import type { SyntheticEvent } from "react";

const LOCAL_IMAGE_BASE = "/static/product-images/amazon";

const KEYWORD_IMAGES: Array<[string[], string]> = [
  [["kindle", "paperwhite", "e-reader", "ereader"], "e-reader.svg"],
  [["ssd", "solid state", "hard drive"], "electronics-storage.svg"],
  [["laptop sleeve"], "electronics-sleeve.svg"],
  [["fitness tracker", "smart watch", "smartwatch", "watch"], "wearable.svg"],
  [["cable tray", "cable management"], "electronics-accessory.svg"],
  [["screen cleaning kit", "cleaning kit", "bluetooth tracker", "item tracker"], "electronics-accessory.svg"],
  [["trackpad", "phone case", "screen protector", "power strip"], "electronics-accessory.svg"],
  [["cleaning supplies", "cleaning cloth", "cleaning cloths", "microfiber cleaning", "non-toxic cleaning"], "home-cleaning.svg"],
  [["messenger bag", "lunch bag", "hiking backpack", "waterproof backpack", "backpack with rain cover", "backpack"], "bag.svg"],
  [["dual monitor", "laptop desk", "laptop stand", "notebook stand", "monitor stand", "monitor arm", "monitor arms", "standing desk", "standing desks", "desk riser", "desk divider", "privacy panel"], "office-furniture.svg"],
  [["desktop organizer", "desktop organizers", "desk organizer", "desk organizers", "workspace organizer", "workspace organizers", "office caddy", "file holder", "file organizer", "file organizers", "letter tray", "paper tray", "paper organizer", "paper organizers", "pen holder", "pen holders", "pencil holder", "pencil holders", "file sorter"], "office-organizer.svg"],
  [["memo board", "sticky note holder", "planner", "journal", "pencil"], "office-supplies.svg"],
  [["air purifier", "hepa filter"], "home-appliance.svg"],
  [["stand mixer", "small appliance", "small appliances", "coffee maker", "espresso", "espresso machine", "pour-over", "coffee dripper"], "kitchen-appliance.svg"],
  [["bottle opener", "can opener", "kitchen funnel", "funnel", "silverware", "utensil tray", "cutlery", "flatware"], "kitchen-cookware.svg"],
  [["vacuum insulated", "insulated stainless", "water bottle"], "kitchen-drinkware.svg"],
  [["office desk drawer organizer", "office desk drawer organizers", "desk drawer organizer"], "office-organizer.svg"],
  [["bathroom", "vanity drawer", "vanity organizer", "home organizer", "drawer organizers set"], "home-organizer.svg"],
  [["storage bin", "storage bins", "plastic storage"], "home-organizer.svg"],
  [["headphone stand", "charger stand", "wireless charger stand"], "electronics-accessory.svg"],
  [["webcam", "webcams"], "electronics-accessory.svg"],
  [["earbud", "headphone", "speaker", "microphone"], "electronics-audio.svg"],
  [["monitor light", "light bar", "cooling pad"], "electronics-accessory.svg"],
  [["dual monitor", "laptop desk"], "office-furniture.svg"],
  [["chair", "office chair", "standing desk", "standing desks", "desk riser", "laptop stand", "notebook stand", "monitor stand", "monitor arm", "monitor arms"], "office-furniture.svg"],
  [["keyboard", "keyboards", "cable", "cables", "hub", "adapter", "desk lamp", "lamp", "phone grip", "mouse", "mice", "light bulb"], "electronics-accessory.svg"],
  [["charger", "chargers", "charging", "usb"], "electronics-accessory.svg"],
  [["security camera", "smart home"], "electronics-accessory.svg"],
  [["monitor", "laptop", "ultrabook"], "electronics-computer.svg"],
  [["book light"], "electronics-accessory.svg"],
  [["french press"], "kitchen-appliance.svg"],
  [["diffuser", "aromatherapy diffuser", "aromatherapy", "essential oil", "scented candle", "candle"], "home-fragrance.svg"],
  [["yoga", "pilates", "exercise mat", "yoga & pilates"], "sports-yoga.svg"],
  [["foam roller", "foam rollers", "recovery & foam rollers"], "sports-fitness.svg"],
  [["workout guide", "strength training"], "sports-fitness.svg"],
  [["book", "novel", "cookbook", "guide", "habits", "leadership", "python", "publishing"], "book.svg"],
  [["green tea", "tea", "coffee", "snack"], "grocery.svg"],
  [["serum", "toothbrush", "cream", "conditioner", "sunscreen", "supplement", "collagen", "scrub", "vitamin", "lotion", "retinol", "moisturizer", "moisturizing", "hydrator", "hyaluronic", "niacinamide"], "health-beauty.svg"],
  [["robot vacuum", "vacuum cleaner", "floor vacuum"], "home-appliance.svg"],
  [["ladle", "opener", "chopper", "masher", "measuring spoon", "colander", "food cover", "ceramic knife", "knife set"], "kitchen-cookware.svg"],
  [["bottle", "mug", "tumbler", "drinkware"], "kitchen-drinkware.svg"],
  [["bath towel", "towel set", "pillow", "pillowcase", "blanket", "sheet", "sheets", "bedding", "linens", "duvet", "comforter"], "home-linens.svg"],
  [["pan", "cookware", "utensil", "cutting board", "kettle", "food storage", "spice rack", "kitchen mat", "container", "dutch oven", "bowl", "spatula"], "kitchen-cookware.svg"],
  [["shirt", "short", "jacket", "jean", "sock", "chino", "hoodie", "polo", "t-shirt", "pants", "dress", "sweater"], "clothing.svg"],
  [["wallet", "purse", "belt", "leather wallet"], "personal-accessory.svg"],
  [["yoga mat"], "sports-yoga.svg"],
  [["dumbbell", "resistance", "hammock", "headlamp", "roller", "camping", "fitness", "trail"], "sports-fitness.svg"],
  [["puzzle", "blocks", "board game", "card game", "remote control", "science kit", "tile set", "train set"], "toy-game.svg"],
  [["pen", "marker", "shredder", "sticky", "laminating", "document", "file", "notebook", "whiteboard"], "office-supplies.svg"],
];

const CATEGORY_IMAGES: Record<string, string> = {
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
};

function keywordMatches(haystack: string, keyword: string, tokens: Set<string>) {
  if (keyword.includes(" ") || keyword.includes("-")) {
    const escaped = keyword.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "[\\s-]+");
    return new RegExp(`(^|[^a-z0-9])${escaped}([^a-z0-9]|$)`).test(haystack);
  }
  return tokens.has(keyword) || tokens.has(`${keyword}s`);
}

export function amazonCategoryImage(category: string) {
  const filename = CATEGORY_IMAGES[category.toLowerCase()] ?? "generic-product.svg";
  return `${LOCAL_IMAGE_BASE}/${filename}`;
}

export function amazonProductFallbackImage({
  name,
  category,
  subcategory,
}: {
  name?: string;
  category?: string;
  subcategory?: string;
}) {
  const parts = [name, subcategory, category].filter(Boolean).join(" ").toLowerCase();
  const tokens = new Set(parts.match(/[a-z0-9]+/g) ?? []);
  for (const [keywords, filename] of KEYWORD_IMAGES) {
    if (keywords.some((keyword) => keywordMatches(parts, keyword, tokens))) {
      return `${LOCAL_IMAGE_BASE}/${filename}`;
    }
  }
  return amazonCategoryImage(category ?? "");
}

export function useFallbackImage(
  event: SyntheticEvent<HTMLImageElement>,
  options: { name?: string; category?: string; subcategory?: string },
) {
  const img = event.currentTarget;
  const fallbackSrc = amazonProductFallbackImage(options);
  if (img.dataset.fallbackApplied === "true") {
    img.style.display = "none";
    img.nextElementSibling?.classList.add("visible");
    return;
  }
  img.dataset.fallbackApplied = "true";
  img.src = fallbackSrc;
  img.style.display = "";
}
