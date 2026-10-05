from __future__ import annotations

import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from breakingweb.backend.amazon_images import (
    _CATEGORY_FALLBACKS,
    _KEYWORD_IMAGES,
    resolve_amazon_product_image,
    resolve_amazon_product_metadata,
)
from breakingweb.backend.seeders.amazon import (
    _MAX_REAL_IMAGE_REUSE,
    _REAL_PRODUCT_IMAGE_CATEGORIES,
    _REAL_PRODUCT_IMAGE_COUNTS,
)
from breakingweb.backend.routes.amazon import (
    AddToCartRequest,
    PlaceOrderRequest,
    ReturnRequest,
    _enrich_order,
    _enrich_return,
    add_to_cart,
    create_return,
    get_cart,
    get_order,
    get_return,
    list_returns,
    list_orders,
    place_order,
)
from breakingweb.backend.state import SessionManager, materialize_task_state
from breakingweb.tasks._registry import env_tasks


PROJECT_ROOT = Path(__file__).resolve().parents[4]
FRONTEND_FALLBACKS_PATH = PROJECT_ROOT / "breakingweb/environments/amazon/src/imageFallbacks.ts"
AMAZON_LOCAL_IMAGE_DIR = PROJECT_ROOT / "breakingweb/static/product-images/amazon"


def test_amazon_task_registry_imports_without_seeder_image_cycle():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from breakingweb.tasks._registry import env_tasks; "
                "assert any(task.task_id == 'amazon_search_and_buy' for task in env_tasks('amazon'))"
            ),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def _frontend_keyword_images() -> tuple[tuple[tuple[str, ...], str], ...]:
    text = FRONTEND_FALLBACKS_PATH.read_text()
    match = re.search(r"const KEYWORD_IMAGES:[^=]+=\s*\[(.*?)\];", text, re.DOTALL)
    assert match, "Could not find frontend KEYWORD_IMAGES"
    entries: list[tuple[tuple[str, ...], str]] = []
    for keywords_text, filename in re.findall(r"\[\[(.*?)\],\s*\"([A-Za-z0-9_-]+\.svg)\"\]", match.group(1)):
        entries.append((tuple(re.findall(r"\"([^\"]+)\"", keywords_text)), filename))
    return tuple(entries)


def _frontend_category_images() -> dict[str, str]:
    text = FRONTEND_FALLBACKS_PATH.read_text()
    match = re.search(r"const CATEGORY_IMAGES:[^{]+=\s*\{(.*?)\};", text, re.DOTALL)
    assert match, "Could not find frontend CATEGORY_IMAGES"
    return dict(re.findall(r"\"([^\"]+)\":\s*\"([A-Za-z0-9_-]+\.svg)\"", match.group(1)))


def test_amazon_image_resolver_keeps_real_urls_but_replaces_random_placeholders():
    real_url = "https://m.media-amazon.com/images/I/71example._AC_UL320_.jpg"
    assert resolve_amazon_product_image(
        name="Sony WH-1000XM5 Wireless Headphones",
        category="Electronics",
        provided_url=real_url,
    ) == real_url

    assert resolve_amazon_product_image(
        name="Sony WH-1000XM5 Wireless Headphones",
        category="Electronics",
        provided_url="https://picsum.photos/seed/headphones/400/400",
    ).endswith("/electronics-audio.svg")


def test_amazon_image_resolver_uses_keyword_matched_local_assets_for_generated_products():
    assert resolve_amazon_product_image(
        name="SoundCore True Wireless Earbuds",
        category="Electronics",
    ).endswith("/electronics-audio.svg")

    assert resolve_amazon_product_image(
        name="Bamboo Cutting Board Set",
        category="Home & Kitchen",
    ).endswith("/kitchen-cookware.svg")

    assert resolve_amazon_product_image(
        name="Gel Pen Multipack",
        category="Office Supplies",
    ).endswith("/office-supplies.svg")

    assert resolve_amazon_product_image(
        name="Classic Leather Wallet",
        category="Electronics",
    ).endswith("/personal-accessory.svg")

    assert resolve_amazon_product_image(
        name="Leather Messenger Bag",
        category="Clothing",
        subcategory="Socks & Underwear",
    ).endswith("/bag.svg")

    assert resolve_amazon_product_image(
        name="Insulated Lunch Bag",
        category="Home & Kitchen",
        subcategory="Kitchen Utensils & Gadgets",
    ).endswith("/bag.svg")

    assert resolve_amazon_product_image(
        name="40L Waterproof Yoga & Pilates Backpack with Rain Cover",
        category="Sports & Outdoors",
        subcategory="Yoga Mats",
    ).endswith("/bag.svg")

    assert resolve_amazon_product_image(
        name="Stretch Chino Pants",
        category="Clothing",
    ).endswith("/clothing.svg")

    assert resolve_amazon_product_image(
        name="Category fallback product",
        category="Sports",
    ).endswith("/sports-fitness.svg")

    assert resolve_amazon_product_image(
        name="Category fallback product",
        category="Toys",
    ).endswith("/toy-game.svg")

    assert resolve_amazon_product_image(
        name="Category fallback product",
        category="Beauty",
    ).endswith("/health-beauty.svg")

    assert resolve_amazon_product_image(
        name="Category fallback product",
        category="Office",
    ).endswith("/office-supplies.svg")

    assert resolve_amazon_product_image(
        name="Premium Yoga Mat",
        category="Sports & Outdoors",
        subcategory="Hydration & Water Bottles",
    ).endswith("/sports-yoga.svg")

    assert resolve_amazon_product_image(
        name="UltraWide Monitor 34-inch",
        category="Electronics",
        subcategory="Speakers",
    ).endswith("/electronics-computer.svg")

    assert resolve_amazon_product_image(
        name="Robot Vacuum Cleaner",
        category="Home & Kitchen",
        subcategory="Bedding & Linens",
    ).endswith("/home-appliance.svg")

    assert resolve_amazon_product_image(
        name="Silicone Phone Grip",
        category="Electronics",
        subcategory="Speakers",
    ).endswith("/electronics-accessory.svg")

    assert resolve_amazon_product_image(
        name="Portable SSD 1TB",
        category="Electronics",
        subcategory="Speakers",
    ).endswith("/electronics-storage.svg")

    assert resolve_amazon_product_image(
        name="Ultrabook Laptop Sleeve 14-inch",
        category="Electronics",
        subcategory="Speakers",
    ).endswith("/electronics-sleeve.svg")

    assert resolve_amazon_product_image(
        name="Performance Running Jacket",
        category="Clothing",
        subcategory="Socks & Underwear",
    ).endswith("/clothing.svg")

    assert resolve_amazon_product_image(
        name="32oz Vacuum Insulated Stainless Steel Drinkware & Water Bottles",
        category="Home & Kitchen",
        subcategory="Vacuums & Floor Care",
    ).endswith("/kitchen-drinkware.svg")

    assert resolve_amazon_product_image(
        name="Professional Stand Mixer",
        category="Home & Kitchen",
        subcategory="Bedding & Linens",
    ).endswith("/kitchen-appliance.svg")

    assert resolve_amazon_product_image(
        name="Organic Cotton Bath Towel Set",
        category="Home & Kitchen",
        subcategory="Cookware & Bakeware",
    ).endswith("/home-linens.svg")

    assert resolve_amazon_product_image(
        name="Memory Foam Pillow",
        category="Home & Kitchen",
        subcategory="Cookware & Bakeware",
    ).endswith("/home-linens.svg")

    assert resolve_amazon_product_image(
        name="Silk Pillowcase Set of 2",
        category="Home & Kitchen",
        subcategory="Cookware & Bakeware",
    ).endswith("/home-linens.svg")

    assert resolve_amazon_product_image(
        name="OTOTO The Original Nessie Ladle",
        category="Home & Kitchen",
        subcategory="Bedding & Linens",
    ).endswith("/kitchen-cookware.svg")

    assert resolve_amazon_product_image(
        name="Daily Planner Journal",
        category="Office Supplies",
        subcategory="Desk Chairs & Seating",
    ).endswith("/office-supplies.svg")

    assert resolve_amazon_product_image(
        name="Mechanical Pencil Set Premium",
        category="Office Supplies",
        subcategory="Desk Chairs & Seating",
    ).endswith("/office-supplies.svg")

    assert resolve_amazon_product_image(
        name="MDOZQ Office Desk Accessories 2pcs Computer Monitor Memo Board Message Board Supplies",
        category="Office Supplies",
        subcategory="Computer Monitors",
    ).endswith("/office-supplies.svg")

    assert resolve_amazon_product_image(
        name="NexGen Audio Ultra Smart Keyboards with Voice Control",
        category="Electronics",
        subcategory="Keyboards",
    ).endswith("/electronics-accessory.svg")

    assert resolve_amazon_product_image(
        name="1080p Webcams with Ring Light and Dual Microphone",
        category="Electronics",
        subcategory="Webcams",
    ).endswith("/electronics-accessory.svg")

    assert resolve_amazon_product_image(
        name="NexGen Audio Slim 4K HDMI 2.1 Cables 10ft Braided",
        category="Electronics",
        subcategory="Cables",
    ).endswith("/electronics-accessory.svg")

    assert resolve_amazon_product_image(
        name="Standing Desk Cable Tray",
        category="Office Supplies",
        subcategory="Standing Desks & Converters",
    ).endswith("/electronics-accessory.svg")

    assert resolve_amazon_product_image(
        name="Studio Monitor Headphones Pro",
        category="Electronics",
        subcategory="Headphones",
    ).endswith("/electronics-audio.svg")

    assert resolve_amazon_product_image(
        name="Amazon Basics Bluetooth Headphones True Wireless Earbuds IPX4Waterproof, in-Ear w/Mic,Charging Case, Black",
        category="Electronics",
        subcategory="Earbuds",
    ).endswith("/electronics-audio.svg")

    assert resolve_amazon_product_image(
        name="Apple AirPods 4 Wireless Earbuds, Bluetooth Headphones, Personalized Spatial Audio, Sweat and Water Resistant, USB-C Charging Case",
        category="Electronics",
        subcategory="Earbuds",
    ).endswith("/electronics-audio.svg")

    assert resolve_amazon_product_image(
        name="Amazon Basics Wired Earbuds with Microphone, In-Ear Headphones, 3.5mm Jack, High Definition Sound, Secure Fit, 4.2 ft Cable",
        category="Electronics",
        subcategory="Earbuds",
    ).endswith("/electronics-audio.svg")

    assert resolve_amazon_product_image(
        name="Smart Home Security Camera Headphones",
        category="Electronics",
        subcategory="Headphones",
    ).endswith("/electronics-audio.svg")

    assert resolve_amazon_product_image(
        name="Bouldercraft Summit Yoga & Pilates Set with Workout Guide",
        category="Sports & Outdoors",
        subcategory="Yoga Mats",
    ).endswith("/sports-yoga.svg")

    assert resolve_amazon_product_image(
        name="TerraPulse Ultralight Recovery & Foam Rollers Set with Workout Guide",
        category="Sports & Outdoors",
        subcategory="Recovery & Foam Rollers",
    ).endswith("/sports-fitness.svg")

    assert resolve_amazon_product_image(
        name="RapidStrike Summit Strength Training Set with Workout Guide",
        category="Sports & Outdoors",
        subcategory="Strength Training",
    ).endswith("/sports-fitness.svg")

    assert resolve_amazon_product_image(
        name="Stainless Steel French Press",
        category="Home & Kitchen",
        subcategory="Cookware & Bakeware",
    ).endswith("/kitchen-appliance.svg")

    assert resolve_amazon_product_image(
        name="LED Book Light",
        category="Office Supplies",
        subcategory="Standing Desks & Converters",
    ).endswith("/electronics-accessory.svg")

    assert resolve_amazon_product_image(
        name="Aromatherapy Diffuser Set",
        category="Home & Kitchen",
        subcategory="Cookware & Bakeware",
    ).endswith("/home-fragrance.svg")

    assert resolve_amazon_product_image(
        name="Aromatherapy Candle Set",
        category="Home & Kitchen",
        subcategory="Home Decor & Accents",
    ).endswith("/home-fragrance.svg")

    assert resolve_amazon_product_image(
        name="Luxury Scented Candle Set",
        category="Home & Kitchen",
        subcategory="Kitchen Utensils & Gadgets",
    ).endswith("/home-fragrance.svg")

    assert resolve_amazon_product_image(
        name="Aromatherapy Essential Oil Set",
        category="Health & Beauty",
        subcategory="Hair Care & Styling",
    ).endswith("/home-fragrance.svg")

    assert resolve_amazon_product_image(
        name="NexGen Audio Elite Portable Mice",
        category="Electronics",
        subcategory="Mice",
    ).endswith("/electronics-accessory.svg")

    assert resolve_amazon_product_image(
        name="Smart Wi-Fi LED Light Bulb 4-Pack",
        category="Electronics",
        subcategory="Headphones",
    ).endswith("/electronics-accessory.svg")

    assert resolve_amazon_product_image(
        name="LED Monitor Light Bar",
        category="Electronics",
        subcategory="Computer Monitors",
    ).endswith("/electronics-accessory.svg")

    assert resolve_amazon_product_image(
        name="Dual Monitor Stand Riser",
        category="Office Supplies",
        subcategory="Computer Monitors",
    ).endswith("/office-furniture.svg")

    assert resolve_amazon_product_image(
        name="Noise-Cancelling Headphone Stand",
        category="Electronics",
        subcategory="Headphones",
    ).endswith("/electronics-accessory.svg")

    assert resolve_amazon_product_image(
        name="Pro Wireless Charger Stand",
        category="Electronics",
        subcategory="Chargers & Power Adapters",
    ).endswith("/electronics-accessory.svg")

    assert resolve_amazon_product_image(
        name="DeskPro Premium Laptop Desk Organizers with Cooling Vents",
        category="Office Supplies",
        subcategory="Desk Organizers",
    ).endswith("/office-furniture.svg")

    assert resolve_amazon_product_image(
        name="Ceramic Pour-Over Coffee Dripper",
        category="Home & Kitchen",
        subcategory="Cleaning Supplies",
    ).endswith("/kitchen-appliance.svg")

    assert resolve_amazon_product_image(
        name="8-Piece Artisan Cleaning Supplies Collection Non-Toxic",
        category="Home & Kitchen",
        subcategory="Cleaning Supplies",
    ).endswith("/home-cleaning.svg")

    assert resolve_amazon_product_image(
        name="Microfiber Cleaning Cloth Set",
        category="Home & Kitchen",
        subcategory="Cookware & Bakeware",
    ).endswith("/home-cleaning.svg")

    assert resolve_amazon_product_image(
        name="Breville BES870XL Espresso Machine",
        category="Home & Kitchen",
        subcategory="Bedding & Linens",
    ).endswith("/kitchen-appliance.svg")

    assert resolve_amazon_product_image(
        name="Glass Food Storage Set 12-Piece",
        category="Home & Kitchen",
        subcategory="Bedding & Linens",
    ).endswith("/kitchen-cookware.svg")

    assert resolve_amazon_product_image(
        name="Bamboo Spice Rack Organizer",
        category="Home & Kitchen",
        subcategory="Drinkware & Water Bottles",
    ).endswith("/kitchen-cookware.svg")

    assert resolve_amazon_product_image(
        name="Premium Silicone Kitchen Mat",
        category="Home & Kitchen",
        subcategory="Drinkware & Water Bottles",
    ).endswith("/kitchen-cookware.svg")

    assert resolve_amazon_product_image(
        name="Ceramic Knife Set 5-Piece",
        category="Home & Kitchen",
        subcategory="Drinkware & Water Bottles",
    ).endswith("/kitchen-cookware.svg")

    assert resolve_amazon_product_image(
        name="KitchenAid Classic Multifunction Can Opener and Bottle Opener",
        category="Home & Kitchen",
        subcategory="Kitchen Utensils & Gadgets",
    ).endswith("/kitchen-cookware.svg")

    assert resolve_amazon_product_image(
        name="KongNai Kitchen Funnel Set 4 Pack, Small and Large, Kitchen Gadgets Accessories Foldable Silicone Collapsible Funnels for Filling Water Bottles",
        category="Home & Kitchen",
        subcategory="Kitchen Utensils & Gadgets",
    ).endswith("/kitchen-cookware.svg")

    assert resolve_amazon_product_image(
        name="Air Purifier HEPA Filter",
        category="Home & Kitchen",
        subcategory="Bedding & Linens",
    ).endswith("/home-appliance.svg")

    assert resolve_amazon_product_image(
        name="Plastic Storage Bins",
        category="Home & Kitchen",
        subcategory="Bedding & Linens",
    ).endswith("/home-organizer.svg")

    assert resolve_amazon_product_image(
        name="Vtopmart 25 PCS Office Desk Drawer Organizers Set, 4-Size Versatile Plastic Drawer Organizer Trays, Storage Bins",
        category="Office Supplies",
        subcategory="Storage & Organization",
    ).endswith("/office-organizer.svg")

    assert resolve_amazon_product_image(
        name="Desk Organizer with Drawer and Pen Holder, 5-Tier Paper Letter Tray Organizer with File Holder",
        category="Office Supplies",
        subcategory="Desk Organizers",
    ).endswith("/office-organizer.svg")

    assert resolve_amazon_product_image(
        name="LETURE Desktop Organizer with Drawer, Accessories Stationary Organizer Desk Caddy, Pen/Pencil/Business Card",
        category="Office Supplies",
        subcategory="Pencils & Writing Supplies",
    ).endswith("/office-organizer.svg")

    assert resolve_amazon_product_image(
        name="Vtopmart 25 PCS Clear Plastic Drawer Organizers Set, 4-Size Versatile Bathroom and Vanity Drawer Organizer Trays",
        category="Home & Kitchen",
        subcategory="Home Decor & Accents",
    ).endswith("/home-organizer.svg")

    assert resolve_amazon_product_image(
        name="Lifewit Silverware Drawer Organizer, Expandable Utensil Tray for Kitchen, BPA Free Flatware and Cutlery Holder",
        category="Home & Kitchen",
        subcategory="Food Storage & Organization",
    ).endswith("/kitchen-cookware.svg")

    assert resolve_amazon_product_image(
        name="Smart Bluetooth Tracker 4-Pack",
        category="Electronics",
        subcategory="Speakers",
    ).endswith("/electronics-accessory.svg")

    assert resolve_amazon_product_image(
        name="Screen Cleaning Kit",
        category="Electronics",
        subcategory="Earbuds",
    ).endswith("/electronics-accessory.svg")

    assert resolve_amazon_product_image(
        name="Entry Level Smartwatch",
        category="Electronics",
        subcategory="Headphones",
    ).endswith("/wearable.svg")

    assert resolve_amazon_product_image(
        name="Smart Watch, Fitness Tracker with Heart Rate Monitor, Blood Oxygen, Sleep Tracking, 1.5 Inch Touchscreen Smartwatch",
        category="Electronics",
        subcategory="Computer Monitors",
    ).endswith("/wearable.svg")

    assert resolve_amazon_product_image(
        name="The Ordinary Natural Moisturizing Factors + Hyaluronic Acid, Lightweight Hydrator for Skin Barrier Support & Hydration",
        category="Health & Beauty",
        subcategory="Face Moisturizers",
    ).endswith("/health-beauty.svg")

    assert resolve_amazon_product_image(
        name="Wireless Trackpad Pro",
        category="Electronics",
        subcategory="Headphones",
    ).endswith("/electronics-accessory.svg")

    assert resolve_amazon_product_image(
        name="Basic Phone Case",
        category="Electronics",
        subcategory="Earbuds",
    ).endswith("/electronics-accessory.svg")

    assert resolve_amazon_product_image(
        name="Phone Screen Protector",
        category="Electronics",
        subcategory="Headphones",
    ).endswith("/electronics-accessory.svg")

    assert resolve_amazon_product_image(
        name="Smart Power Strip 6-Outlet",
        category="Electronics",
        subcategory="Earbuds",
    ).endswith("/electronics-accessory.svg")

    assert resolve_amazon_product_image(
        name="Noise-Cancelling Desk Divider Panel Set",
        category="Office Supplies",
        subcategory="Desk Dividers & Panels",
    ).endswith("/office-furniture.svg")


def test_amazon_frontend_and_backend_image_fallback_rules_stay_in_sync():
    assert _frontend_keyword_images() == _KEYWORD_IMAGES
    assert _frontend_category_images() == _CATEGORY_FALLBACKS


def test_amazon_frontend_local_image_references_exist():
    static_prefix = "/static/product-images/amazon/"
    frontend_src = PROJECT_ROOT / "breakingweb/environments/amazon/src"
    source_files = sorted(
        path
        for pattern in ("*.ts", "*.tsx", "*.css")
        for path in frontend_src.rglob(pattern)
    )
    missing: list[str] = []
    for source_file in source_files:
        text = source_file.read_text()
        filenames = set(re.findall(r"/static/product-images/amazon/([A-Za-z0-9_-]+\.svg)", text))
        if source_file.name == "imageFallbacks.ts":
            filenames.update(re.findall(r'"([A-Za-z0-9_-]+\.svg)"', text))

        for filename in filenames:
            asset_path = PROJECT_ROOT / "breakingweb/static/product-images/amazon" / filename
            if not asset_path.exists():
                missing.append(f"{source_file.relative_to(PROJECT_ROOT)}:{static_prefix}{filename}")

    assert not missing, "\n".join(missing)


def test_amazon_frontend_product_image_elements_use_local_fallbacks():
    frontend_src = PROJECT_ROOT / "breakingweb/environments/amazon/src"
    offenders: list[str] = []
    for source_file in sorted(frontend_src.rglob("*.tsx")):
        text = source_file.read_text()
        for match in re.finditer(r"<img\b(?:(?!/>).)*?/>", text, re.DOTALL):
            img_markup = match.group(0)
            if "image_url" not in img_markup:
                continue
            if "onError" not in img_markup or "useFallbackImage" not in img_markup:
                line_no = text[:match.start()].count("\n") + 1
                offenders.append(f"{source_file.relative_to(PROJECT_ROOT)}:{line_no}")

    assert not offenders, "\n".join(offenders)


def test_amazon_frontend_order_like_image_fallbacks_keep_category_context():
    frontend_src = PROJECT_ROOT / "breakingweb/environments/amazon/src"
    offenders: list[str] = []
    for relative in [
        "components/CartItem.tsx",
        "pages/Checkout.tsx",
        "pages/OrderConfirmation.tsx",
        "pages/Orders.tsx",
        "pages/ReturnForm.tsx",
        "pages/Returns.tsx",
    ]:
        source_file = frontend_src / relative
        text = source_file.read_text()
        for match in re.finditer(r"useFallbackImage\(e,\s*\{(.*?)\}\)", text, re.DOTALL):
            options = match.group(1)
            if "product_name" not in options:
                continue
            if "category:" not in options or "subcategory:" not in options:
                line_no = text[:match.start()].count("\n") + 1
                offenders.append(f"{source_file.relative_to(PROJECT_ROOT)}:{line_no}")

    assert not offenders, "\n".join(offenders)


def test_amazon_frontend_keeps_desktop_shopping_structure():
    search = (PROJECT_ROOT / "breakingweb/environments/amazon/src/pages/Search.tsx").read_text()
    product_detail = (PROJECT_ROOT / "breakingweb/environments/amazon/src/pages/ProductDetail.tsx").read_text()

    search_required = [
        'className="search-filters"',
        'aria-label="Search filters"',
        "Department",
        "Customer Review",
        "Price",
        'className="search-results__sort"',
        'className="search-result-item__image"',
        'className="search-result-item__title"',
        'className="search-result-item__rating"',
        'className="search-result-item__price"',
        'className="search-result-item__delivery"',
    ]
    product_detail_required = [
        'className="product-detail__image-col"',
        'className="product-detail__title"',
        'className="product-detail__rating"',
        'className="product-detail__pricing"',
        'className="product-detail__buy-col"',
        'className="product-detail__buy-box"',
        'data-action="add-to-cart"',
        "Buy Now",
    ]

    missing = [
        f"Search.tsx:{text}" for text in search_required if text not in search
    ] + [
        f"ProductDetail.tsx:{text}"
        for text in product_detail_required
        if text not in product_detail
    ]

    assert not missing, "\n".join(missing)


def test_amazon_local_image_assets_stay_lightweight_and_valid():
    assets = sorted(AMAZON_LOCAL_IMAGE_DIR.iterdir())
    assert len(assets) <= 40

    non_svg = [asset.name for asset in assets if asset.suffix != ".svg"]
    assert not non_svg

    total_bytes = sum(asset.stat().st_size for asset in assets)
    assert total_bytes <= 160_000

    oversized = [f"{asset.name}:{asset.stat().st_size}" for asset in assets if asset.stat().st_size > 8_000]
    assert not oversized

    invalid: list[str] = []
    for asset in assets:
        text = asset.read_text()
        if "<script" in text.lower():
            invalid.append(f"{asset.name}:script tag")
        external_refs = [
            ref
            for ref in re.findall(r"(?:href|src)=[\"']([^\"']+)[\"']", text, flags=re.I)
            if ref.startswith(("http://", "https://", "//"))
        ]
        if external_refs:
            invalid.append(f"{asset.name}:external refs={external_refs}")
        try:
            root = ET.parse(asset).getroot()
        except ET.ParseError as exc:
            invalid.append(f"{asset.name}:{exc}")
            continue
        if not root.tag.endswith("svg"):
            invalid.append(f"{asset.name}:root={root.tag}")

    assert not invalid, "\n".join(invalid)


def test_amazon_seeded_products_never_use_random_placeholder_images():
    offenders: list[str] = []
    for task in env_tasks("amazon"):
        _, state, _, _ = materialize_task_state("amazon", task.task_id, seed=42)
        for product in state.products:
            if not product.image_url or "picsum.photos" in product.image_url:
                offenders.append(f"{task.task_id}:{product.id}:{product.name}:{product.image_url}")

    assert not offenders


def test_amazon_seeded_product_images_are_valid_across_multiple_seeds():
    offenders: list[str] = []
    static_prefix = "/static/product-images/amazon/"
    for seed in (0, 1):
        for task in env_tasks("amazon"):
            _, state, _, _ = materialize_task_state("amazon", task.task_id, seed=seed)
            for product in state.products:
                image_url = product.image_url or ""
                if not image_url:
                    offenders.append(f"{seed}:{task.task_id}:{product.id}:{product.name}:missing image_url")
                    continue
                if "picsum.photos" in image_url:
                    offenders.append(f"{seed}:{task.task_id}:{product.id}:{product.name}:{image_url}")
                    continue
                if image_url.startswith(static_prefix):
                    asset = AMAZON_LOCAL_IMAGE_DIR / image_url.removeprefix(static_prefix)
                    if not asset.exists():
                        offenders.append(f"{seed}:{task.task_id}:{product.id}:{product.name}:missing asset {image_url}")

    assert not offenders


def test_amazon_seeded_products_do_not_fall_back_to_generic_local_images():
    offenders: list[str] = []
    for seed in (0, 1, 42):
        for task in env_tasks("amazon"):
            _, state, _, _ = materialize_task_state("amazon", task.task_id, seed=seed)
            for product in state.products:
                if product.image_url.endswith("/generic-product.svg"):
                    offenders.append(
                        f"seed={seed}:{task.task_id}:{product.id}:{product.category}:{product.subcategory}:{product.name}"
                    )

    assert not offenders, "\n".join(offenders[:50])


def test_amazon_target_products_use_semantic_local_images():
    offenders: list[str] = []
    static_prefix = "/static/product-images/amazon/"
    for seed in (0, 1, 42):
        for task in env_tasks("amazon"):
            _, state, targets, _ = materialize_task_state("amazon", task.task_id, seed=seed)
            target_ids: list[str] = []
            for key, value in targets.items():
                if key.endswith("product_id") and isinstance(value, str):
                    target_ids.append(value)
                elif key.endswith("product_ids") and isinstance(value, list):
                    target_ids.extend(item for item in value if isinstance(item, str))

            for product_id in sorted(set(target_ids)):
                product = state.get_product(product_id)
                if product is None:
                    continue
                expected = resolve_amazon_product_image(
                    name=product.name,
                    category=product.category,
                    subcategory=product.subcategory,
                )
                label = f"seed={seed}:{task.task_id}:{product.name}"
                if not product.image_url.startswith(static_prefix):
                    offenders.append(f"{label}:external {product.image_url}")
                elif product.image_url.endswith("/generic-product.svg"):
                    offenders.append(f"{label}:generic fallback")
                elif product.image_url != expected:
                    offenders.append(
                        f"{label}:expected {expected}, got {product.image_url}"
                    )

    assert not offenders, "\n".join(offenders[:50])


def test_amazon_seeded_products_do_not_use_high_reuse_scraped_images():
    high_reuse_urls = {
        url
        for url, count in _REAL_PRODUCT_IMAGE_COUNTS.items()
        if count > _MAX_REAL_IMAGE_REUSE
    }
    offenders: list[str] = []
    for task in env_tasks("amazon"):
        _, state, _, _ = materialize_task_state("amazon", task.task_id, seed=42)
        for product in state.products:
            if product.image_url in high_reuse_urls:
                offenders.append(f"{task.task_id}:{product.id}:{product.name}:{product.image_url}")

    assert not offenders


def test_amazon_seeded_products_do_not_use_cross_category_reused_scraped_images():
    cross_category_urls = {
        url
        for url, categories in _REAL_PRODUCT_IMAGE_CATEGORIES.items()
        if len(categories) > 1
    }
    offenders: list[str] = []
    for task in env_tasks("amazon"):
        _, state, _, _ = materialize_task_state("amazon", task.task_id, seed=42)
        for product in state.products:
            if product.image_url in cross_category_urls:
                offenders.append(f"{task.task_id}:{product.id}:{product.name}:{product.image_url}")

    assert not offenders


def test_amazon_seeded_non_book_products_do_not_use_book_local_asset():
    offenders: list[str] = []
    for task in env_tasks("amazon"):
        _, state, _, _ = materialize_task_state("amazon", task.task_id, seed=42)
        for product in state.products:
            if product.category != "Books" and product.image_url.endswith("/book.svg"):
                offenders.append(
                    f"{task.task_id}:{product.name}:{product.category}:{product.subcategory}"
                )

    assert not offenders, "\n".join(offenders[:50])


def test_amazon_seeded_office_drawer_organizers_use_office_asset():
    offenders: list[str] = []
    for task in env_tasks("amazon"):
        _, state, _, _ = materialize_task_state("amazon", task.task_id, seed=42)
        for product in state.products:
            name = product.name.lower()
            if product.category == "Office Supplies" and "desk drawer organizer" in name:
                if product.image_url.startswith("/static/") and not product.image_url.endswith("/office-organizer.svg"):
                    offenders.append(
                        f"{task.task_id}:{product.name}:{product.category}:{product.subcategory}:{product.image_url}"
                    )

    assert not offenders, "\n".join(offenders[:50])


def test_amazon_seeded_home_drawer_organizers_do_not_use_office_asset():
    offenders: list[str] = []
    for task in env_tasks("amazon"):
        _, state, _, _ = materialize_task_state("amazon", task.task_id, seed=42)
        for product in state.products:
            name = product.name.lower()
            if product.category == "Home & Kitchen" and "drawer organizer" in name:
                if product.image_url.endswith("/office-organizer.svg"):
                    offenders.append(
                        f"{task.task_id}:{product.name}:{product.category}:{product.subcategory}:{product.image_url}"
                    )

    assert not offenders, "\n".join(offenders[:50])


def test_amazon_seeded_home_cleaning_supplies_use_cleaning_asset():
    offenders: list[str] = []
    for task in env_tasks("amazon"):
        _, state, _, _ = materialize_task_state("amazon", task.task_id, seed=42)
        for product in state.products:
            name = product.name.lower()
            if product.category == "Home & Kitchen" and (
                "cleaning supplies" in name or "cleaning cloth" in name
            ):
                if product.image_url.startswith("/static/") and not product.image_url.endswith("/home-cleaning.svg"):
                    offenders.append(
                        f"{task.task_id}:{product.name}:{product.category}:{product.subcategory}:{product.image_url}"
                    )

    assert not offenders, "\n".join(offenders[:50])


def test_amazon_target_product_display_metadata_is_inferred_from_name():
    metadata = resolve_amazon_product_metadata(name="Premium Yoga Mat", category="Sports & Outdoors")
    assert metadata["subcategory"] == "Yoga Mats"
    assert "yoga mat" in str(metadata["description"]).lower()

    cable_metadata = resolve_amazon_product_metadata(name="4K HDMI Cable 6ft", category="Electronics")
    assert cable_metadata["subcategory"] == "Cables"

    cable_tray_metadata = resolve_amazon_product_metadata(name="Standing Desk Cable Tray", category="Office Supplies")
    assert cable_tray_metadata["subcategory"] == "Cable Management"

    hub_metadata = resolve_amazon_product_metadata(name="USB-C Hub 7-in-1 Multiport Adapter", category="Electronics")
    assert hub_metadata["subcategory"] == "Hubs & Adapters"

    smart_home_metadata = resolve_amazon_product_metadata(
        name="Wavefront Turbo Smart Smart Home with Voice Control",
        category="Electronics",
    )
    assert smart_home_metadata["subcategory"] == "Smart Home Devices"
    assert "voice" in str(smart_home_metadata["description"]).lower()

    camera_metadata = resolve_amazon_product_metadata(
        name="Smart Home Security Camera",
        category="Electronics",
    )
    assert camera_metadata["subcategory"] == "Smart Home Cameras"

    ssd_metadata = resolve_amazon_product_metadata(name="Portable SSD 1TB", category="Electronics")
    assert ssd_metadata["subcategory"] == "External Solid State Drives"

    jacket_metadata = resolve_amazon_product_metadata(name="Performance Running Jacket", category="Clothing")
    assert jacket_metadata["subcategory"] == "Jackets & Outerwear"

    board_metadata = resolve_amazon_product_metadata(name="Bamboo Cutting Board Set", category="Home & Kitchen")
    assert board_metadata["subcategory"] == "Cutting Boards"

    power_bank_metadata = resolve_amazon_product_metadata(
        name="2 Pack Portable Charger, Slimmer 10000mAh Power Bank",
        category="Electronics",
    )
    assert power_bank_metadata["subcategory"] == "Portable Chargers"

    vitamin_metadata = resolve_amazon_product_metadata(
        name="Centrum Adult Multivitamin/Multimineral Supplement",
        category="Health & Beauty",
    )
    assert vitamin_metadata["subcategory"] == "Vitamins & Supplements"

    organizer_metadata = resolve_amazon_product_metadata(
        name="Mesh Desk Organizer and Rotating Pen Holder",
        category="Office Supplies",
    )
    assert organizer_metadata["subcategory"] == "Desk Organizers"

    mixer_metadata = resolve_amazon_product_metadata(
        name="Professional Stand Mixer",
        category="Home & Kitchen",
    )
    assert mixer_metadata["subcategory"] == "Small Appliances"

    insulated_metadata = resolve_amazon_product_metadata(
        name="32oz Vacuum Insulated Stainless Steel Drinkware & Water Bottles",
        category="Home & Kitchen",
    )
    assert insulated_metadata["subcategory"] == "Drinkware & Water Bottles"

    journal_metadata = resolve_amazon_product_metadata(
        name="Daily Planner Journal",
        category="Office Supplies",
    )
    assert journal_metadata["subcategory"] == "Planners & Journals"

    towel_metadata = resolve_amazon_product_metadata(
        name="Organic Cotton Bath Towel Set",
        category="Home & Kitchen",
    )
    assert towel_metadata["subcategory"] == "Bath Towels"

    pillow_metadata = resolve_amazon_product_metadata(
        name="Memory Foam Pillow",
        category="Home & Kitchen",
    )
    assert pillow_metadata["subcategory"] == "Pillows"

    foam_metadata = resolve_amazon_product_metadata(
        name="TerraPulse Ultralight Recovery & Foam Rollers Set with Workout Guide",
        category="Sports & Outdoors",
    )
    assert foam_metadata["subcategory"] == "Recovery & Foam Rollers"

    french_press_metadata = resolve_amazon_product_metadata(
        name="Stainless Steel French Press",
        category="Home & Kitchen",
    )
    assert french_press_metadata["subcategory"] == "Coffee Makers"

    book_light_metadata = resolve_amazon_product_metadata(
        name="LED Book Light",
        category="Office Supplies",
    )
    assert book_light_metadata["subcategory"] == "Reading Lights"

    diffuser_metadata = resolve_amazon_product_metadata(
        name="Aromatherapy Diffuser Set",
        category="Home & Kitchen",
    )
    assert diffuser_metadata["subcategory"] == "Home Fragrance & Diffusers"

    candle_metadata = resolve_amazon_product_metadata(
        name="Luxury Scented Candle Set",
        category="Home & Kitchen",
    )
    assert candle_metadata["subcategory"] == "Home Fragrance & Diffusers"

    mouse_metadata = resolve_amazon_product_metadata(
        name="NexGen Audio Elite Portable Mice",
        category="Electronics",
    )
    assert mouse_metadata["subcategory"] == "Mice"

    light_metadata = resolve_amazon_product_metadata(
        name="Smart Wi-Fi LED Light Bulb 4-Pack",
        category="Electronics",
    )
    assert light_metadata["subcategory"] == "Smart Lighting"

    coffee_dripper_metadata = resolve_amazon_product_metadata(
        name="Ceramic Pour-Over Coffee Dripper",
        category="Home & Kitchen",
    )
    assert coffee_dripper_metadata["subcategory"] == "Coffee Makers"

    storage_metadata = resolve_amazon_product_metadata(
        name="Plastic Storage Bins",
        category="Home & Kitchen",
    )
    assert storage_metadata["subcategory"] == "Storage & Organization"

    headphone_stand_metadata = resolve_amazon_product_metadata(
        name="Noise-Cancelling Headphone Stand",
        category="Electronics",
    )
    assert headphone_stand_metadata["subcategory"] == "Headphone Stands"

    charger_stand_metadata = resolve_amazon_product_metadata(
        name="Pro Wireless Charger Stand",
        category="Electronics",
    )
    assert charger_stand_metadata["subcategory"] == "Charging Stands"

    laptop_desk_metadata = resolve_amazon_product_metadata(
        name="DeskPro Premium Laptop Desk Organizers with Cooling Vents",
        category="Office Supplies",
    )
    assert laptop_desk_metadata["subcategory"] == "Monitor Arms & Laptop Stands"

    knife_metadata = resolve_amazon_product_metadata(
        name="Ceramic Knife Set 5-Piece",
        category="Home & Kitchen",
    )
    assert knife_metadata["subcategory"] == "Kitchen Knives"

    air_purifier_metadata = resolve_amazon_product_metadata(
        name="Air Purifier HEPA Filter",
        category="Home & Kitchen",
    )
    assert air_purifier_metadata["subcategory"] == "Air Purifiers"

    smartwatch_metadata = resolve_amazon_product_metadata(
        name="Entry Level Smartwatch",
        category="Electronics",
    )
    assert smartwatch_metadata["subcategory"] == "Fitness Trackers"

    bag_metadata = resolve_amazon_product_metadata(name="Leather Messenger Bag", category="Clothing")
    assert bag_metadata["subcategory"] == "Bags & Backpacks"
    assert "bag" in str(bag_metadata["description"]).lower()

    _, state, _, _ = materialize_task_state("amazon", "amazon_add_single_item", seed=42)
    wallet = next(p for p in state.products if p.name == "Classic Leather Wallet")
    assert wallet.subcategory == "Wallets & Card Cases"
    assert "wallet" in wallet.description.lower()


def test_amazon_target_products_remain_discoverable_by_name_after_metadata_overrides():
    missing: list[str] = []
    for task in env_tasks("amazon"):
        _, state, targets, _ = materialize_task_state("amazon", task.task_id, seed=42)
        target_names = [
            value
            for key, value in targets.items()
            if key.endswith(("product_name", "_name")) and isinstance(value, str)
        ]
        for name in target_names:
            # Some target names refer to non-product concepts. Treat only names
            # that exactly exist in the catalog as product discoverability checks.
            product = next((p for p in state.products if p.name == name), None)
            if product is None:
                continue
            result_ids = {p.id for p in state.search_products(name)}
            if product.id not in result_ids:
                missing.append(f"{task.task_id}: {name}")

    assert not missing


def test_amazon_target_product_metadata_has_no_obvious_display_mismatches():
    mismatches: list[str] = []
    for task in env_tasks("amazon"):
        _, state, targets, _ = materialize_task_state("amazon", task.task_id, seed=42)
        target_ids: list[str] = []
        for key, value in targets.items():
            if key.endswith("product_id") and isinstance(value, str):
                target_ids.append(value)
            elif key.endswith("product_ids") and isinstance(value, list):
                target_ids.extend(item for item in value if isinstance(item, str))

        for product_id in target_ids:
            product = state.get_product(product_id)
            if product is None:
                continue
            name = product.name.lower()
            text = f"{product.subcategory} {product.description}".lower()
            if "wallet" in name and ("audio" in text or "mice" in text):
                mismatches.append(f"{task.task_id}: {product.name}")
            if ("messenger bag" in name or "lunch bag" in name or "backpack" in name) and (
                "sock" in text or "underwear" in text or "cookware" in text or "yoga mat" in text
            ):
                mismatches.append(f"{task.task_id}: {product.name}")
            if "yoga" in name and ("water bottle" in text or "hydration" in text):
                mismatches.append(f"{task.task_id}: {product.name}")
            if "chair" in name and ("bedding" in text or "home cooks" in text):
                mismatches.append(f"{task.task_id}: {product.name}")
            if "monitor" in name and product.subcategory in {"Speakers", "Webcams", "Earbuds"}:
                mismatches.append(f"{task.task_id}: {product.name}")
            if "tea" in name and ("bedding" in text or "home cooks" in text):
                mismatches.append(f"{task.task_id}: {product.name}")
            if "fitness tracker" in name and ("webcam" in text or "audio" in text):
                mismatches.append(f"{task.task_id}: {product.name}")
            if "phone grip" in name and ("speaker" in text or "audio" in text):
                mismatches.append(f"{task.task_id}: {product.name}")
            if "keyboard" in name and "audio" in text:
                mismatches.append(f"{task.task_id}: {product.name}")
            if "smart home" in name and "audio" in text:
                mismatches.append(f"{task.task_id}: {product.name}")
            if "cable tray" in name and ("monitor arm" in text or "standing desk" in text):
                mismatches.append(f"{task.task_id}: {product.name}")
            if "webcam" in name and "audio" in text:
                mismatches.append(f"{task.task_id}: {product.name}")
            if "ssd" in name and product.subcategory in {"Speakers", "Webcams", "Earbuds"}:
                mismatches.append(f"{task.task_id}: {product.name}")
            if "laptop sleeve" in name and product.subcategory in {"Speakers", "Webcams", "Earbuds"}:
                mismatches.append(f"{task.task_id}: {product.name}")
            if "docking station" in name and product.subcategory in {"Speakers", "Webcams", "Earbuds"}:
                mismatches.append(f"{task.task_id}: {product.name}")
            if "cutting board" in name and ("home decor" in text or "bedding" in text):
                mismatches.append(f"{task.task_id}: {product.name}")
            if "jacket" in name and ("sock" in text or "underwear" in text):
                mismatches.append(f"{task.task_id}: {product.name}")
            if "whiteboard" in name and ("monitor arm" in text or "mount" in text):
                mismatches.append(f"{task.task_id}: {product.name}")
            if ("multivitamin" in name or "vitamin" in name) and (
                "serum" in text or "lotion" in text or "grooming" in text or "hair care" in text
            ):
                mismatches.append(f"{task.task_id}: {product.name}")
            if ("desk organizer" in name or "pen holder" in name or "pencil holder" in name) and (
                "monitor arm" in text or "desk chair" in text or "lighting" in text
            ):
                mismatches.append(f"{task.task_id}: {product.name}")
            if ("power bank" in name or "portable charger" in name) and "portable charger" not in text:
                mismatches.append(f"{task.task_id}: {product.name}")
            if "onion holder" in name and "kitchen utensil" not in text:
                mismatches.append(f"{task.task_id}: {product.name}")
            if "monitor headphone" in name and product.subcategory == "Computer Monitors":
                mismatches.append(f"{task.task_id}: {product.name}")
            if "headphone stand" in name and product.subcategory == "Headphones":
                mismatches.append(f"{task.task_id}: {product.name}")
            if ("charger stand" in name or "wireless charger stand" in name) and product.subcategory == "Office Chairs":
                mismatches.append(f"{task.task_id}: {product.name}")
            if ("dual monitor" in name or "laptop desk" in name) and "computer monitor" in text:
                mismatches.append(f"{task.task_id}: {product.name}")
            if ("ceramic knife" in name or "knife set" in name) and "drinkware" in text:
                mismatches.append(f"{task.task_id}: {product.name}")
            if "air purifier" in name and ("bedding" in text or "linen" in text or "cookware" in text):
                mismatches.append(f"{task.task_id}: {product.name}")

    assert not mismatches


def test_amazon_catalog_product_metadata_has_no_high_frequency_display_mismatches():
    mismatches: list[str] = []
    for task in env_tasks("amazon"):
        _, state, _, _ = materialize_task_state("amazon", task.task_id, seed=42)
        for product in state.products:
            name = product.name.lower()
            text = f"{product.subcategory} {product.description}".lower()
            label = f"{task.task_id}: {product.name} -> {product.subcategory}"

            if ("multivitamin" in name or "vitamin" in name) and (
                "serum" in text or "lotion" in text or "grooming" in text or "hair care" in text
            ):
                mismatches.append(label)
            if ("messenger bag" in name or "lunch bag" in name or "backpack" in name) and (
                "sock" in text or "underwear" in text or "cookware" in text or "yoga mat" in text
            ):
                mismatches.append(label)
            if ("power bank" in name or "portable charger" in name) and "portable charger" not in text:
                mismatches.append(label)
            if ("keyboard" in name or "webcam" in name or "cable" in name or "hub" in name) and "audio" in text:
                mismatches.append(label)
            if "smart home" in name and "audio" in text:
                mismatches.append(label)
            if "cable tray" in name and ("monitor arm" in text or "standing desk" in text):
                mismatches.append(label)
            if ("desk organizer" in name or "desk organizers" in name or "pen holder" in name or "pencil holder" in name) and (
                "desk chair" in text or "computer monitor" in text or "keyboard" in text or "lighting" in text
            ):
                mismatches.append(label)
            if ("planner" in name or "journal" in name or "pencil" in name or "memo board" in name) and (
                "desk chair" in text or "office chair" in text or "computer monitor" in text
            ):
                mismatches.append(label)
            if ("file organizer" in name or "letter tray" in name or "paper organizer" in name) and (
                "desk chair" in text or "computer monitor" in text or "keyboard" in text or "lighting" in text
            ):
                mismatches.append(label)
            if "onion holder" in name and "kitchen utensil" not in text:
                mismatches.append(label)
            if "vacuum insulated" in name and "vacuum" in text and "water bottle" not in text and "drinkware" not in text:
                mismatches.append(label)
            if "stand mixer" in name and (
                "desk chair" in text or "office chair" in text or "monitor arm" in text or "bedding" in text
            ):
                mismatches.append(label)
            if "monitor headphone" in name and "computer monitor" in text:
                mismatches.append(label)
            if ("bath towel" in name or "pillow" in name or "pillowcase" in name) and (
                "cookware" in text or "kitchen utensil" in text or "bakeware" in text
            ):
                mismatches.append(label)
            if (
                "diffuser" in name
                or "candle" in name
                or "essential oil" in name
                or "aromatherapy" in name
            ) and ("cookware" in text or "bakeware" in text or "vitamin" in text or "hair care" in text):
                mismatches.append(label)
            if ("mice" in name or "mouse" in name) and "audio" in text:
                mismatches.append(label)
            if "light bulb" in name and ("audio" in text or "headphone" in text or "earbud" in text):
                mismatches.append(label)
            if ("monitor stand" in name or "monitor arm" in name or "laptop stand" in name) and (
                "computer monitor" in text or "audio" in text
            ):
                mismatches.append(label)
            if ("pour-over" in name or "coffee dripper" in name) and "tea" in text:
                mismatches.append(label)
            if "storage bin" in name and ("bedding" in text or "linen" in text):
                mismatches.append(label)
            if "headphone stand" in name and "headphones" in text and "stand" not in product.subcategory.lower():
                mismatches.append(label)
            if ("charger stand" in name or "wireless charger stand" in name) and "office chair" in text:
                mismatches.append(label)
            if ("dual monitor" in name or "laptop desk" in name) and "computer monitor" in text:
                mismatches.append(label)
            if ("ceramic knife" in name or "knife set" in name) and "drinkware" in text:
                mismatches.append(label)
            if "air purifier" in name and ("bedding" in text or "linen" in text or "cookware" in text):
                mismatches.append(label)
            if "espresso" in name and ("bedding" in text or "linen" in text or "cookware" in text):
                mismatches.append(label)
            if "food storage" in name and ("bedding" in text or "linen" in text):
                mismatches.append(label)
            if ("spice rack" in name or "kitchen mat" in name) and "drinkware" in text:
                mismatches.append(label)

    assert not mismatches, "\n".join(mismatches[:50])


def test_amazon_order_responses_include_product_image_context_for_confirmation_pages():
    session_manager = SessionManager()
    session_id, _, _ = session_manager.create_session("amazon", "amazon_search_and_buy", seed=42)
    state = session_manager.get(session_id)
    product = next(p for p in state.products if p.name == "Sony WH-1000XM5 Wireless Headphones")

    add_to_cart(
        AddToCartRequest(session_id=session_id, product_id=product.id, quantity=1),
        session_manager=session_manager,
    )

    cart_response = get_cart(session_id=session_id, session_manager=session_manager)
    assert cart_response["items"][0]["image_url"] == product.image_url
    assert cart_response["items"][0]["category"] == product.category
    assert cart_response["items"][0]["subcategory"] == product.subcategory

    checkout_response = place_order(
        PlaceOrderRequest(
            session_id=session_id,
            shipping_address_id=state.addresses[0].id,
            payment_method_id=state.payment_methods[0].id,
        ),
        session_manager=session_manager,
    )

    order = checkout_response["order"]
    assert order["items"][0]["image_url"] == product.image_url
    assert order["items"][0]["category"] == product.category
    assert order["items"][0]["subcategory"] == product.subcategory

    order_response = get_order(
        order["id"],
        session_id=session_id,
        session_manager=session_manager,
    )
    assert order_response["order"]["items"][0]["image_url"] == product.image_url
    assert order_response["order"]["items"][0]["category"] == product.category
    assert order_response["order"]["items"][0]["subcategory"] == product.subcategory

    orders_response = list_orders(
        session_id=session_id,
        page=1,
        page_size=50,
        session_manager=session_manager,
    )
    listed_order = next(o for o in orders_response["items"] if o["id"] == order["id"])
    assert listed_order["items"][0]["image_url"] == product.image_url
    assert listed_order["items"][0]["category"] == product.category
    assert listed_order["items"][0]["subcategory"] == product.subcategory

    return_response = create_return(
        ReturnRequest(
            session_id=session_id,
            order_id=order["id"],
            order_item_index=0,
            reason="no_longer_needed",
        ),
        session_manager=session_manager,
    )
    ret = return_response["return"]
    assert ret["image_url"] == product.image_url
    assert ret["category"] == product.category
    assert ret["subcategory"] == product.subcategory

    get_return_response = get_return(ret["id"], session_id=session_id, session_manager=session_manager)
    assert get_return_response["return"]["image_url"] == product.image_url
    assert get_return_response["return"]["category"] == product.category
    assert get_return_response["return"]["subcategory"] == product.subcategory

    list_returns_response = list_returns(session_id=session_id, session_manager=session_manager)
    listed_return = next(r for r in list_returns_response["items"] if r["id"] == ret["id"])
    assert listed_return["image_url"] == product.image_url
    assert listed_return["category"] == product.category
    assert listed_return["subcategory"] == product.subcategory


def test_amazon_product_image_context_enrichment_overwrites_empty_image_url():
    session_manager = SessionManager()
    session_id, _, _ = session_manager.create_session("amazon", "amazon_search_and_buy", seed=42)
    state = session_manager.get(session_id)
    product = next(p for p in state.products if p.name == "Sony WH-1000XM5 Wireless Headphones")

    order_payload = {
        "id": "order_null_image",
        "items": [
            {
                "product_id": product.id,
                "product_name": product.name,
                "quantity": 1,
                "unit_price": product.price,
                "image_url": None,
            }
        ],
    }
    enriched_order = _enrich_order(state, order_payload)
    assert enriched_order["items"][0]["image_url"] == product.image_url
    assert enriched_order["items"][0]["category"] == product.category
    assert enriched_order["items"][0]["subcategory"] == product.subcategory

    return_payload = {
        "id": "return_null_image",
        "product_id": product.id,
        "product_name": product.name,
        "image_url": None,
    }
    enriched_return = _enrich_return(state, return_payload)
    assert enriched_return["image_url"] == product.image_url
    assert enriched_return["category"] == product.category
    assert enriched_return["subcategory"] == product.subcategory
