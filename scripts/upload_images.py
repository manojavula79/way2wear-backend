"""
WAY2WEAR — IMAGE UPLOADER
Uploads the product images you already have locally (from the Kaggle
dataset) to Supabase Storage, then updates each product's `image`
column with the permanent public URL.

Run ONCE. Images then load forever, with no dependency on Myntra.

SETUP (do these first):
  1. In Supabase dashboard → Storage → create a PUBLIC bucket named:  products
  2. Add two values to your backend .env file:
        SUPABASE_URL=https://dylwsskmmjqnvmfmxzkq.supabase.co
        SUPABASE_SERVICE_KEY=<your service_role key from Settings → API>
  3. pip install supabase asyncpg python-dotenv

HOW TO RUN (from way2wear-backend folder, venv active):
    python scripts/upload_images.py

The IMAGES_DIR below must point to the dataset's images folder on your PC.
"""

import os
import ssl
import asyncio

import asyncpg
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL  = os.getenv("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY   = os.getenv("SUPABASE_SERVICE_KEY", "")
RAW_DB_URL    = os.getenv("DATABASE_URL", "")
DB_URL        = RAW_DB_URL.replace("postgresql+asyncpg://", "postgresql://").split("?")[0]

BUCKET = "products"

# ── EDIT THIS to where you unzipped the dataset images ──
# It should be the folder that directly contains 15970.jpg, 39386.jpg, etc.
IMAGES_DIR = r"C:\Users\DELL\Downloads\archive - Copy\images"


def ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def public_url(filename: str) -> str:
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{filename}"


async def main():
    # Sanity checks
    if not (SUPABASE_URL and SERVICE_KEY):
        print("ERROR: set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
        return
    if not DB_URL:
        print("ERROR: DATABASE_URL not found in .env")
        return
    if not os.path.isdir(IMAGES_DIR):
        print(f"ERROR: images folder not found:\n  {IMAGES_DIR}")
        print("Edit IMAGES_DIR at the top of this script.")
        return

    supabase = create_client(SUPABASE_URL, SERVICE_KEY)

    # Get the products we loaded (IDs look like 'K15970' → file is 15970.jpg)
    conn = await asyncpg.connect(DB_URL, ssl=ssl_ctx(), statement_cache_size=0)
    rows = await conn.fetch("SELECT id FROM products")
    print(f"{len(rows)} products to process.")

    uploaded = 0
    skipped_missing = 0
    updated = 0
    failed = 0

    for i, r in enumerate(rows, 1):
        pid = r["id"]                       # e.g. K15970
        raw_id = pid[1:] if pid.startswith("K") else pid
        filename = f"{raw_id}.jpg"
        local_path = os.path.join(IMAGES_DIR, filename)

        if not os.path.exists(local_path):
            skipped_missing += 1
            continue

        # Upload to Supabase Storage (upsert so re-runs are safe)
        try:
            with open(local_path, "rb") as f:
                supabase.storage.from_(BUCKET).upload(
                    path=filename,
                    file=f.read(),
                    file_options={"content-type": "image/jpeg", "upsert": "true"},
                )
            uploaded += 1
        except Exception as e:
            # "already exists" is fine — file is already up there
            if "exists" not in str(e).lower():
                failed += 1
                if failed <= 5:
                    print(f"  upload failed for {filename}: {e}")
                # still try to set the URL below

        # Update DB with permanent public URL
        try:
            await conn.execute(
                "UPDATE products SET image=$1 WHERE id=$2",
                public_url(filename), pid,
            )
            updated += 1
        except Exception as e:
            print(f"  db update failed for {pid}: {e}")

        if i % 200 == 0:
            print(f"  ... processed {i}/{len(rows)} "
                  f"(uploaded {uploaded}, missing {skipped_missing})")

    await conn.close()

    print("\nDONE.")
    print(f"  Uploaded images : {uploaded}")
    print(f"  DB rows updated  : {updated}")
    print(f"  Missing locally  : {skipped_missing}")
    print(f"  Failed uploads   : {failed}")
    print(f"\nExample image URL:\n  {public_url('15970.jpg')}")
    print("Open that URL in your browser to confirm it loads.")


if __name__ == "__main__":
    asyncio.run(main())
