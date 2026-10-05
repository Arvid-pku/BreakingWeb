"""Deterministic product image selection for the Amazon environment.

The benchmark needs product images to be stable and at least semantically
aligned with the product text. Scraped Amazon products may carry their original
CDN URL; generated benchmark products use this lightweight local resolver
instead of random placeholder photos.
"""

from __future__ import annotations

import re

LOCAL_IMAGE_BASE = "/static/product-images/amazon"

_KEYWORD_IMAGES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("kindle", "paperwhite", "e-reader", "ereader"), "e-reader.svg"),
    (("ssd", "solid state", "hard drive"), "electronics-storage.svg"),
    (("laptop sleeve",), "electronics-sleeve.svg"),
    (("fitness tracker", "smart watch", "smartwatch", "watch"), "wearable.svg"),
    (("cable tray", "cable management"), "electronics-accessory.svg"),
    (("screen cleaning kit", "cleaning kit", "bluetooth tracker", "item tracker"), "electronics-accessory.svg"),
    (("trackpad", "phone case", "screen protector", "power strip"), "electronics-accessory.svg"),
    (("cleaning supplies", "cleaning cloth", "cleaning cloths", "microfiber cleaning", "non-toxic cleaning"), "home-cleaning.svg"),
    (("messenger bag", "lunch bag", "hiking backpack", "waterproof backpack", "backpack with rain cover", "backpack"), "bag.svg"),
    (("dual monitor", "laptop desk", "laptop stand", "notebook stand", "monitor stand", "monitor arm", "monitor arms", "standing desk", "standing desks", "desk riser", "desk divider", "privacy panel"), "office-furniture.svg"),
    (("desktop organizer", "desktop organizers", "desk organizer", "desk organizers", "workspace organizer", "workspace organizers", "office caddy", "file holder", "file organizer", "file organizers", "letter tray", "paper tray", "paper organizer", "paper organizers", "pen holder", "pen holders", "pencil holder", "pencil holders", "file sorter"), "office-organizer.svg"),
    (("memo board", "sticky note holder", "planner", "journal", "pencil"), "office-supplies.svg"),
    (("air purifier", "hepa filter"), "home-appliance.svg"),
    (("stand mixer", "small appliance", "small appliances", "coffee maker", "espresso", "espresso machine", "pour-over", "coffee dripper"), "kitchen-appliance.svg"),
    (("bottle opener", "can opener", "kitchen funnel", "funnel", "silverware", "utensil tray", "cutlery", "flatware"), "kitchen-cookware.svg"),
    (("vacuum insulated", "insulated stainless", "water bottle"), "kitchen-drinkware.svg"),
    (("office desk drawer organizer", "office desk drawer organizers", "desk drawer organizer"), "office-organizer.svg"),
    (("bathroom", "vanity drawer", "vanity organizer", "home organizer", "drawer organizers set"), "home-organizer.svg"),
    (("storage bin", "storage bins", "plastic storage"), "home-organizer.svg"),
    (("headphone stand", "charger stand", "wireless charger stand"), "electronics-accessory.svg"),
    (("webcam", "webcams"), "electronics-accessory.svg"),
    (("earbud", "headphone", "speaker", "microphone"), "electronics-audio.svg"),
    (("monitor light", "light bar", "cooling pad"), "electronics-accessory.svg"),
    (("dual monitor", "laptop desk"), "office-furniture.svg"),
    (("chair", "office chair", "standing desk", "standing desks", "desk riser", "laptop stand", "notebook stand", "monitor stand", "monitor arm", "monitor arms"), "office-furniture.svg"),
    (("keyboard", "keyboards", "cable", "cables", "hub", "adapter", "desk lamp", "lamp", "phone grip", "mouse", "mice", "light bulb"), "electronics-accessory.svg"),
    (("charger", "chargers", "charging", "usb"), "electronics-accessory.svg"),
    (("security camera", "smart home"), "electronics-accessory.svg"),
    (("monitor", "laptop", "ultrabook"), "electronics-computer.svg"),
    (("book light",), "electronics-accessory.svg"),
    (("french press",), "kitchen-appliance.svg"),
    (("diffuser", "aromatherapy diffuser", "aromatherapy", "essential oil", "scented candle", "candle"), "home-fragrance.svg"),
    (("yoga", "pilates", "exercise mat", "yoga & pilates"), "sports-yoga.svg"),
    (("foam roller", "foam rollers", "recovery & foam rollers"), "sports-fitness.svg"),
    (("workout guide", "strength training"), "sports-fitness.svg"),
    (("book", "novel", "cookbook", "guide", "habits", "leadership", "python", "publishing"), "book.svg"),
    (("green tea", "tea", "coffee", "snack"), "grocery.svg"),
    (("serum", "toothbrush", "cream", "conditioner", "sunscreen", "supplement", "collagen", "scrub", "vitamin", "lotion", "retinol", "moisturizer", "moisturizing", "hydrator", "hyaluronic", "niacinamide"), "health-beauty.svg"),
    (("robot vacuum", "vacuum cleaner", "floor vacuum"), "home-appliance.svg"),
    (("ladle", "opener", "chopper", "masher", "measuring spoon", "colander", "food cover", "ceramic knife", "knife set"), "kitchen-cookware.svg"),
    (("bottle", "mug", "tumbler", "drinkware"), "kitchen-drinkware.svg"),
    (("bath towel", "towel set", "pillow", "pillowcase", "blanket", "sheet", "sheets", "bedding", "linens", "duvet", "comforter"), "home-linens.svg"),
    (("pan", "cookware", "utensil", "cutting board", "kettle", "food storage", "spice rack", "kitchen mat", "container", "dutch oven", "bowl", "spatula"), "kitchen-cookware.svg"),
    (("shirt", "short", "jacket", "jean", "sock", "chino", "hoodie", "polo", "t-shirt", "pants", "dress", "sweater"), "clothing.svg"),
    (("wallet", "purse", "belt", "leather wallet"), "personal-accessory.svg"),
    (("yoga mat",), "sports-yoga.svg"),
    (("dumbbell", "resistance", "hammock", "headlamp", "roller", "camping", "fitness", "trail"), "sports-fitness.svg"),
    (("puzzle", "blocks", "board game", "card game", "remote control", "science kit", "tile set", "train set"), "toy-game.svg"),
    (("pen", "marker", "shredder", "sticky", "laminating", "document", "file", "notebook", "whiteboard"), "office-supplies.svg"),
)

_CATEGORY_FALLBACKS: dict[str, str] = {
    "electronics": "electronics-accessory.svg",
    "books": "book.svg",
    "home & kitchen": "kitchen-cookware.svg",
    "home": "kitchen-cookware.svg",
    "kitchen": "kitchen-cookware.svg",
    "clothing": "clothing.svg",
    "sports & outdoors": "sports-fitness.svg",
    "sports": "sports-fitness.svg",
    "toys & games": "toy-game.svg",
    "toys": "toy-game.svg",
    "health & beauty": "health-beauty.svg",
    "health": "health-beauty.svg",
    "beauty": "health-beauty.svg",
    "office supplies": "office-supplies.svg",
    "office": "office-supplies.svg",
}

_NAME_METADATA: tuple[tuple[tuple[str, ...], dict[str, object]], ...] = (
    (("earbud",), {
        "subcategory": "Earbuds",
        "description": "True wireless earbuds with portable charging, clear audio, and everyday comfort for calls and music.",
        "features": ["Wireless charging case", "Built-in microphone", "Comfort fit"],
    }),
    (("headphone stand",), {
        "subcategory": "Headphone Stands",
        "description": "A desktop headphone stand for storing headsets, keeping a desk organized, and protecting audio gear.",
        "features": ["Desktop storage", "Headset support", "Cable-friendly design"],
    }),
    (("headphone",), {
        "subcategory": "Headphones",
        "description": "Wireless headphones designed for comfortable listening, clear calls, and reliable battery life.",
        "features": ["Wireless audio", "Built-in microphone", "Long battery life"],
    }),
    (("speaker",), {
        "subcategory": "Speakers",
        "description": "A portable speaker built for clear sound, easy wireless pairing, and everyday listening.",
        "features": ["Bluetooth connectivity", "Portable design", "Clear sound"],
    }),
    (("power bank", "portable charger"), {
        "subcategory": "Portable Chargers",
        "description": "A portable power bank for charging phones, tablets, and travel devices away from an outlet.",
        "features": ["Portable battery pack", "USB-C charging", "Travel ready"],
    }),
    (("charger stand", "wireless charger stand"), {
        "subcategory": "Charging Stands",
        "description": "A charging stand for holding and powering phones or small devices on a desk or nightstand.",
        "features": ["Upright charging", "Desk ready", "Compact footprint"],
    }),
    (("charger", "charging"), {
        "subcategory": "Chargers & Power Adapters",
        "description": "A compact charging accessory for keeping phones, tablets, and everyday devices powered up.",
        "features": ["Fast charging support", "Compact design", "Travel friendly"],
    }),
    (("cable tray", "cable management"), {
        "subcategory": "Cable Management",
        "description": "A cable management accessory for routing cords, organizing desk wires, and keeping a workstation tidy.",
        "features": ["Desk cable routing", "Cord organization", "Workspace cleanup"],
    }),
    (("cable",), {
        "subcategory": "Cables",
        "description": "A durable cable accessory for charging, syncing, or connecting everyday electronics.",
        "features": ["Durable jacket", "Reliable connection", "Travel friendly"],
    }),
    (("hub", "adapter", "hubs & adapters"), {
        "subcategory": "Hubs & Adapters",
        "description": "A compact hub or adapter for connecting laptops, tablets, monitors, and everyday USB-C accessories.",
        "features": ["Multiport connectivity", "USB-C compatible", "Travel friendly"],
    }),
    (("keyboard",), {
        "subcategory": "Keyboards",
        "description": "A responsive keyboard for desktop setups, productivity, and everyday typing.",
        "features": ["Responsive keys", "Compact layout", "Desktop ready"],
    }),
    (("mouse", "mice"), {
        "subcategory": "Mice",
        "description": "An ergonomic mouse for everyday navigation, travel, and desktop productivity.",
        "features": ["Ergonomic shape", "Wireless connection", "Smooth tracking"],
    }),
    (("webcam",), {
        "subcategory": "Webcams",
        "description": "A webcam for clear video calls, streaming, and remote meetings.",
        "features": ["HD video", "Built-in microphone", "Easy mounting"],
    }),
    (("light bulb", "smart wi-fi led light"), {
        "subcategory": "Smart Lighting",
        "description": "A smart LED light bulb for app-controlled home lighting, schedules, and everyday room illumination.",
        "features": ["Smart app control", "Energy-efficient LED", "Voice assistant compatible"],
    }),
    (("security camera", "smart home security camera"), {
        "subcategory": "Smart Home Cameras",
        "description": "A smart home security camera for monitoring indoor spaces, motion events, and live video from a phone.",
        "features": ["Live video monitoring", "Motion alerts", "Easy smart home setup"],
    }),
    (("smart home",), {
        "subcategory": "Smart Home Devices",
        "description": "A smart home device for voice-controlled rooms, connected routines, and everyday home automation.",
        "features": ["Voice control", "Smart home routines", "Connected device setup"],
    }),
    (("monitor light", "light bar"), {
        "subcategory": "Monitor Light Bars",
        "description": "A monitor light bar for illuminating a desk without screen glare during work, reading, and calls.",
        "features": ["Screen-safe lighting", "Adjustable brightness", "Desk setup friendly"],
    }),
    (("cooling pad",), {
        "subcategory": "Laptop Cooling Pads",
        "description": "A laptop cooling pad that raises a notebook computer and helps move heat away during long work sessions.",
        "features": ["Raised laptop support", "Cooling airflow", "Desk setup friendly"],
    }),
    (("docking station", "dock"), {
        "subcategory": "Docking Stations",
        "description": "A multiport docking station for connecting laptops to monitors, peripherals, and power at a desk.",
        "features": ["Multiport connectivity", "Laptop compatible", "Desktop cable management"],
    }),
    (("ssd", "solid state"), {
        "subcategory": "External Solid State Drives",
        "description": "A portable solid state drive for fast file transfers, backups, and expanded storage.",
        "features": ["Fast transfer speeds", "Portable storage", "Shock-resistant design"],
    }),
    (("laptop sleeve",), {
        "subcategory": "Laptop Sleeves",
        "description": "A slim protective laptop sleeve for carrying and protecting a notebook computer during travel.",
        "features": ["Padded protection", "Slim profile", "Travel friendly"],
    }),
    (("memo board", "sticky note holder"), {
        "subcategory": "Memo Boards & Note Holders",
        "description": "A desktop memo board and sticky note holder for organizing reminders, messages, and workspace notes.",
        "features": ["Desktop note display", "Sticky note storage", "Office organization"],
    }),
    (("planner", "journal"), {
        "subcategory": "Planners & Journals",
        "description": "A planner journal for schedules, notes, goals, and daily office or school organization.",
        "features": ["Dated planning pages", "Notes sections", "Portable format"],
    }),
    (("pencil",), {
        "subcategory": "Pencils & Writing Supplies",
        "description": "A writing supply set for note taking, sketching, drafting, and everyday office or school use.",
        "features": ["Smooth writing", "Office ready", "School supply essential"],
    }),
    (("book light",), {
        "subcategory": "Reading Lights",
        "description": "A compact reading light for books, desks, travel, and focused nighttime reading.",
        "features": ["LED lighting", "Clip-on design", "Portable reading aid"],
    }),
    (("wallet", "leather wallet"), {
        "subcategory": "Wallets & Card Cases",
        "description": "A slim everyday wallet with genuine leather, RFID blocking, and organized card storage for daily carry.",
        "features": ["Genuine leather", "RFID blocking", "Slim bifold design"],
    }),
    (("messenger bag", "lunch bag", "hiking backpack", "waterproof backpack", "backpack with rain cover", "backpack"), {
        "subcategory": "Bags & Backpacks",
        "description": "A carry bag or backpack for travel, commuting, packed lunches, or everyday essentials.",
        "features": ["Carry-friendly design", "Organized storage", "Everyday use"],
    }),
    (("yoga", "exercise mat"), {
        "subcategory": "Yoga Mats",
        "description": "A cushioned non-slip yoga mat designed for floor workouts, stretching, pilates, and daily practice.",
        "features": ["Non-slip surface", "Extra thick cushioning", "Carrying strap included"],
    }),
    (("foam roller", "foam rollers", "recovery & foam rollers"), {
        "subcategory": "Recovery & Foam Rollers",
        "description": "A foam roller or recovery set for stretching, mobility work, and post-workout muscle care.",
        "features": ["Portable recovery tool", "Textured support", "Workout ready"],
    }),
    (("dual monitor", "laptop desk", "laptop stand", "monitor stand", "monitor arm", "monitor arms", "standing desk", "standing desks", "desk riser"), {
        "subcategory": "Monitor Arms & Laptop Stands",
        "description": "An adjustable desk stand for lifting a laptop or monitor into a more ergonomic working position.",
        "features": ["Adjustable height", "Stable desktop base", "Ergonomic viewing angle"],
    }),
    (("monitor",), {
        "subcategory": "Computer Monitors",
        "description": "A wide desktop monitor with sharp resolution, modern connectivity, and a smooth refresh rate for work and entertainment.",
        "features": ["Wide display", "USB-C connectivity", "Adjustable stand"],
    }),
    (("green tea", "tea"), {
        "subcategory": "Tea",
        "description": "A bulk pack of individually wrapped organic green tea bags for hot or iced tea at home or in the office.",
        "features": ["USDA Organic certified", "Individually wrapped bags", "Antioxidant rich"],
    }),
    (("french press",), {
        "subcategory": "Coffee Makers",
        "description": "A French press coffee maker for brewing rich coffee at home, work, or while hosting.",
        "features": ["Manual brewing", "Reusable filter", "Coffee service ready"],
    }),
    (("diffuser", "aromatherapy diffuser", "aromatherapy", "essential oil", "scented candle", "candle"), {
        "subcategory": "Home Fragrance & Diffusers",
        "description": "A home fragrance item for adding scent, aromatherapy, or ambient fragrance to bedrooms, offices, and living spaces.",
        "features": ["Home fragrance", "Aromatherapy ready", "Compact tabletop design"],
    }),
    (("robot vacuum", "vacuum cleaner", "floor vacuum"), {
        "subcategory": "Vacuums & Floor Care",
        "description": "A compact robot vacuum cleaner built for automated floor cleaning, scheduled runs, and everyday dust pickup.",
        "features": ["Automatic cleaning", "Low-profile design", "Rechargeable base"],
    }),
    (("air purifier", "hepa filter"), {
        "subcategory": "Air Purifiers",
        "description": "A HEPA air purifier for filtering dust, allergens, and everyday household air particles.",
        "features": ["HEPA filtration", "Compact room coverage", "Quiet operation"],
    }),
    (("vacuum insulated", "insulated stainless", "water bottle"), {
        "subcategory": "Drinkware & Water Bottles",
        "description": "An insulated stainless steel bottle or drinkware item for keeping beverages hot or cold during everyday use.",
        "features": ["Insulated stainless steel", "Reusable drinkware", "Travel friendly"],
    }),
    (("espresso", "espresso machine"), {
        "subcategory": "Espresso Machines",
        "description": "A countertop espresso machine for brewing espresso drinks, steaming milk, and making coffee at home.",
        "features": ["Countertop espresso brewing", "Milk steaming support", "Home coffee setup"],
    }),
    (("stand mixer",), {
        "subcategory": "Small Appliances",
        "description": "A countertop stand mixer for mixing dough, batter, and everyday baking recipes.",
        "features": ["Countertop mixer", "Multiple speeds", "Baking ready"],
    }),
    (("small appliance", "small appliances"), {
        "subcategory": "Small Appliances",
        "description": "A countertop kitchen appliance for everyday prep, brewing, cooking, or serving at home.",
        "features": ["Countertop friendly", "Kitchen ready", "Everyday prep support"],
    }),
    (("pour-over", "coffee dripper"), {
        "subcategory": "Coffee Makers",
        "description": "A pour-over coffee dripper or set for manual brewing at home, work, or while hosting.",
        "features": ["Manual coffee brewing", "Reusable setup", "Kitchen counter ready"],
    }),
    (("bath towel", "towel set"), {
        "subcategory": "Bath Towels",
        "description": "A soft towel set for bath, guest, and everyday home linen use.",
        "features": ["Soft cotton feel", "Absorbent weave", "Machine washable"],
    }),
    (("pillow", "pillowcase"), {
        "subcategory": "Pillows",
        "description": "A comfortable pillow for bed, couch, guest room, or everyday home use.",
        "features": ["Soft support", "Home comfort", "Machine washable cover"],
    }),
    (("blanket", "sheet", "sheets", "bedding", "linens", "duvet", "comforter"), {
        "subcategory": "Bedding & Linens",
        "description": "A home linen item for bedding, layering, guest rooms, or everyday comfort.",
        "features": ["Soft fabric", "Easy care", "Home ready"],
    }),
    (("cutting board",), {
        "subcategory": "Cutting Boards",
        "description": "A durable cutting board set for meal prep, chopping, serving, and everyday kitchen use.",
        "features": ["Food-safe surface", "Easy cleanup", "Kitchen prep ready"],
    }),
    (("ceramic knife", "knife set"), {
        "subcategory": "Kitchen Knives",
        "description": "A kitchen knife set for slicing, chopping, and everyday meal preparation.",
        "features": ["Sharp cutting edges", "Kitchen prep ready", "Easy storage"],
    }),
    (("kettle",), {
        "subcategory": "Kettles",
        "description": "A stainless steel kettle for heating and pouring water for coffee, tea, and daily kitchen use.",
        "features": ["Stainless steel body", "Controlled pour", "Comfortable handle"],
    }),
    (("water bottle",), {
        "subcategory": "Water Bottles",
        "description": "A reusable stainless steel water bottle for hydration at home, work, school, or outdoors.",
        "features": ["Insulated design", "Leak-resistant lid", "Reusable bottle"],
    }),
    (("food storage",), {
        "subcategory": "Food Storage & Organization",
        "description": "A kitchen food storage set for leftovers, pantry organization, meal prep, and everyday containers.",
        "features": ["Airtight storage", "Kitchen organization", "Meal prep ready"],
    }),
    (("spice rack",), {
        "subcategory": "Kitchen Storage & Organization",
        "description": "A spice rack organizer for arranging seasonings, pantry items, and everyday kitchen supplies.",
        "features": ["Kitchen organization", "Pantry-ready storage", "Easy-access tiers"],
    }),
    (("kitchen mat",), {
        "subcategory": "Kitchen Mats",
        "description": "A silicone kitchen mat for counter prep, baking, sink-side protection, or everyday kitchen use.",
        "features": ["Silicone surface", "Easy cleanup", "Kitchen counter protection"],
    }),
    (("silverware", "utensil tray", "cutlery", "flatware"), {
        "subcategory": "Kitchen Drawer Organizers",
        "description": "A kitchen drawer organizer tray for sorting silverware, utensils, flatware, and everyday cooking tools.",
        "features": ["Expandable tray", "Utensil storage", "Kitchen drawer organization"],
    }),
    (("bathroom", "vanity drawer", "vanity organizer"), {
        "subcategory": "Bathroom & Vanity Organizers",
        "description": "A household organizer tray set for bathroom drawers, vanity storage, and small home essentials.",
        "features": ["Multiple tray sizes", "Drawer organization", "Home storage"],
    }),
    (("onion holder", "onion slicer", "slicer holder"), {
        "subcategory": "Kitchen Utensils & Gadgets",
        "description": "A kitchen slicing tool for holding onions, tomatoes, and other produce during prep.",
        "features": ["Stainless steel tines", "Stable slicing guide", "Easy cleanup"],
    }),
    (("fitness tracker", "smart watch", "smartwatch", "watch"), {
        "subcategory": "Fitness Trackers",
        "description": "A wearable fitness tracker for steps, workouts, heart-rate monitoring, and everyday activity goals.",
        "features": ["Activity tracking", "Heart-rate monitor", "Long battery life"],
    }),
    (("phone grip",), {
        "subcategory": "Cell Phone Grips & Stands",
        "description": "A compact silicone phone grip that adds a secure hold and doubles as a simple stand for everyday phone use.",
        "features": ["Secure grip", "Collapsible stand", "Adhesive backing"],
    }),
    (("chair",), {
        "subcategory": "Office Chairs",
        "description": "An ergonomic office chair with supportive seating and adjustable comfort for long desk sessions.",
        "features": ["Ergonomic support", "Adjustable height", "Padded seat"],
    }),
    (("whiteboard", "dry erase"), {
        "subcategory": "Whiteboards & Boards",
        "description": "A dry erase whiteboard for planning, notes, meetings, and classroom or office organization.",
        "features": ["Dry erase surface", "Wall-mount ready", "Marker tray included"],
    }),
    (("desk divider",), {
        "subcategory": "Desk Dividers & Panels",
        "description": "A desk divider panel for separating workspace areas and adding privacy on shared desks.",
        "features": ["Desktop privacy panel", "Office workspace support", "Easy placement"],
    }),
    (("file organizer", "letter tray", "paper organizer"), {
        "subcategory": "File Organizers",
        "description": "A file and paper organizer for sorting folders, letter trays, and desktop documents.",
        "features": ["Multi-tier storage", "Letter-size document slots", "Desktop organization"],
    }),
    (("desk organizer", "desk organizers", "pen holder", "pencil holder"), {
        "subcategory": "Desk Organizers",
        "description": "A desktop organizer for sorting pens, notes, files, and everyday office supplies.",
        "features": ["Multiple compartments", "Desktop storage", "Office organization"],
    }),
    (("office desk drawer organizer", "office desk drawer organizers", "desk drawer organizer"), {
        "subcategory": "Drawer Organizers",
        "description": "A desk drawer organizer tray set for sorting office supplies, accessories, and workspace essentials.",
        "features": ["Multiple tray sizes", "Drawer organization", "Office supply storage"],
    }),
    (("running jacket", "puffer jacket", "jacket"), {
        "subcategory": "Jackets & Outerwear",
        "description": "A lightweight jacket for running, travel, layering, and everyday weather protection.",
        "features": ["Lightweight shell", "Easy layering", "Weather-resistant fabric"],
    }),
    (("resistance band", "resistance bands"), {
        "subcategory": "Resistance Bands",
        "description": "A resistance band set for strength training, stretching, recovery, and home workouts.",
        "features": ["Multiple resistance levels", "Portable workout kit", "Includes carrying pouch"],
    }),
    (("multivitamin", "vitamin"), {
        "subcategory": "Vitamins & Supplements",
        "description": "A daily vitamin supplement formulated to support wellness, nutrition, and everyday health needs.",
        "features": ["Daily supplement", "Vitamin and mineral support", "Wellness focused"],
    }),
    (("storage bin", "storage bins", "plastic storage"), {
        "subcategory": "Storage & Organization",
        "description": "A household storage bin for organizing closets, shelves, pantry items, or general home supplies.",
        "features": ["Stackable storage", "Home organization", "Durable plastic bin"],
    }),
    (("kindle", "paperwhite", "e-reader", "ereader"), {
        "subcategory": "E-Readers",
        "description": "A lightweight e-reader with a glare-free display, long battery life, and ample storage for books.",
        "features": ["Glare-free display", "Long battery life", "Water-resistant design"],
    }),
)


def _keyword_matches(haystack: str, keyword: str, tokens: set[str]) -> bool:
    """Match full words or short phrases without accidental substrings."""
    if " " in keyword or "-" in keyword:
        pattern = r"(?<![a-z0-9])" + re.escape(keyword).replace(r"\ ", r"[\s-]+") + r"(?![a-z0-9])"
        return re.search(pattern, haystack) is not None
    return keyword in tokens or f"{keyword}s" in tokens


def resolve_amazon_product_metadata(
    *,
    name: str,
    category: str | None = None,
) -> dict[str, object]:
    """Return optional display metadata inferred from product name.

    This is intentionally conservative and only covers products whose task
    builder category/subcategory can be noisy. It does not affect product IDs,
    prices, ratings, or task targets.
    """
    haystack = name.lower()
    tokens = set(re.findall(r"[a-z0-9]+", haystack))
    for keywords, metadata in _NAME_METADATA:
        if any(_keyword_matches(haystack, keyword, tokens) for keyword in keywords):
            return dict(metadata)
    return {}


def resolve_amazon_product_image(
    *,
    name: str,
    category: str,
    subcategory: str | None = None,
    provided_url: str | None = None,
) -> str:
    """Return a stable image URL for a product.

    Real scraped products keep their provided image URL, except for known
    random placeholder services. Generated products fall back to a tiny local
    image set keyed by product text and category.
    """
    if provided_url and "picsum.photos" not in provided_url:
        return provided_url

    name_haystack = name.lower()
    name_tokens = set(re.findall(r"[a-z0-9]+", name_haystack))
    for keywords, filename in _KEYWORD_IMAGES:
        if any(_keyword_matches(name_haystack, keyword, name_tokens) for keyword in keywords):
            return f"{LOCAL_IMAGE_BASE}/{filename}"

    haystack = " ".join(part for part in (name, subcategory or "", category) if part).lower()
    tokens = set(re.findall(r"[a-z0-9]+", haystack))
    for keywords, filename in _KEYWORD_IMAGES:
        if any(_keyword_matches(haystack, keyword, tokens) for keyword in keywords):
            return f"{LOCAL_IMAGE_BASE}/{filename}"

    filename = _CATEGORY_FALLBACKS.get(category.lower(), "generic-product.svg")
    return f"{LOCAL_IMAGE_BASE}/{filename}"
