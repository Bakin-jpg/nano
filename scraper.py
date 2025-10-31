# scraper.py (Revisi dengan Logika Terpisah untuk Metadata dan Episode)

import json
import time
import os
import re
from playwright.sync_api import sync_playwright, TimeoutError
from bs4 import BeautifulSoup

DATABASE_FILE = "anime_database.json"

def load_database():
    """Memuat database dari file JSON. Menggunakan metadata_url sebagai kunci unik."""
    if os.path.exists(DATABASE_FILE):
        try:
            with open(DATABASE_FILE, 'r', encoding='utf-8') as f:
                print(f"Database '{DATABASE_FILE}' ditemukan dan dimuat.")
                # Gunakan metadata_url sebagai kunci unik untuk pencarian cepat
                return {show['metadata_url']: show for show in json.load(f)}
        except json.JSONDecodeError:
            print(f"[PERINGATAN] File database '{DATABASE_FILE}' rusak. Memulai dari awal.")
            return {}
    print(f"Database '{DATABASE_FILE}' tidak ditemukan. Akan membuat yang baru.")
    return {}

def save_database(data_dict):
    """Menyimpan data dari dictionary kembali ke file JSON, diurutkan berdasarkan judul."""
    sorted_data = sorted(data_dict.values(), key=lambda x: x.get('title', ''))
    with open(DATABASE_FILE, 'w', encoding='utf-8') as f:
        json.dump(sorted_data, f, ensure_ascii=False, indent=4)
    print(f"Database berhasil disimpan ke '{DATABASE_FILE}'.")

def scrape_main_page_shows(page):
    """
    Mengambil daftar anime dari halaman utama.
    Memisahkan URL untuk metadata (dari judul) dan URL untuk episode (dari thumbnail).
    """
    url = "https://kickass-anime.ru/"
    print("\n=== TAHAP 1: MENGAMBIL DAFTAR ANIME DARI HALAMAN UTAMA ===")
    shows = {}
    try:
        page.goto(url, timeout=120000)
        page.wait_for_selector('div.latest-update div.show-item', timeout=60000)
        
        # Scroll untuk memuat semua item
        last_height = page.evaluate("document.body.scrollHeight")
        while True:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == last_height: break
            last_height = new_height
            
        html_content = page.content()
        soup = BeautifulSoup(html_content, 'html.parser')

        for item in soup.find_all('div', class_='show-item'):
            try:
                title_element = item.find('h2', class_='show-title').find('a')
                thumbnail_link_element = item.find('a', class_='show-poster')

                title = title_element.text.strip()
                metadata_url = "https://kickass-anime.ru" + title_element['href']
                episode_page_url = "https://kickass-anime.ru" + thumbnail_link_element['href']

                if metadata_url not in shows:
                    shows[metadata_url] = {
                        'title': title,
                        'metadata_url': metadata_url,
                        'episode_page_url': episode_page_url
                    }
            except (AttributeError, IndexError):
                continue
                
        print(f"Menemukan {len(shows)} anime unik di halaman utama.")
        return list(shows.values())
    except Exception as e:
        print(f"[ERROR di Tahap 1] Gagal mengambil daftar anime: {e}")
        return []

def scrape_show_metadata(page, metadata_url):
    """Hanya fokus mengambil metadata dari halaman detail anime."""
    print(f"   - Mengambil metadata dari: {metadata_url}")
    details = {"poster_image_url": "N/A", "synopsis": "N/A", "genres": [], "type": "N/A", "year": "N/A"}
    try:
        page.goto(metadata_url, timeout=90000, wait_until='domcontentloaded')
        page.wait_for_selector("div.banner-section div.v-image__image", timeout=30000)

        details["poster_image_url"] = page.locator("div.banner-section div.v-image__image").first.get_attribute("style").split('url("')[1].split('")')[0]
        details["synopsis"] = page.locator("div.v-card__text div.text-caption").inner_text(timeout=5000)
        details["genres"] = [g.inner_text() for g in page.locator(".anime-info-card .v-card__text span.v-chip__content").all()]
        info_texts = [info.inner_text() for info in page.locator(".anime-info-card .d-flex.mt-2.mb-3 div.text-subtitle-2").all()]
        details["type"] = next((text for text in info_texts if text in ["TV", "Movie", "OVA", "ONA", "Special"]), "N/A")
        details["year"] = next((text for text in info_texts if re.match(r'^\d{4}$', text)), "N/A")
        print("     Metadata berhasil diambil.")
    except Exception as e:
        print(f"     [PERINGATAN] Gagal mengambil metadata: {e}")
    return details

def scrape_show_episodes(page, episode_page_url, existing_episode_numbers):
    """
    Hanya fokus mengambil iframe episode dari halaman "Watch Now".
    Tidak ada interaksi dengan dropdown Sub/Dub.
    """
    print(f"   - Mengecek episode dari: {episode_page_url}")
    newly_scraped_episodes = []
    try:
        page.goto(episode_page_url, timeout=90000)
        page.wait_for_selector("div.episode-item", timeout=60000)

        all_on_page_ep_nums = [el.locator("span.v-chip__content").inner_text() for el in page.locator("div.episode-item").all()]
        
        episodes_to_scrape_nums = sorted(
            [ep_num for ep_num in all_on_page_ep_nums if ep_num not in existing_episode_numbers],
            key=lambda x: int(''.join(filter(str.isdigit, x.split()[-1])) or 0)
        )

        if not episodes_to_scrape_nums:
            print("     Tidak ada episode baru untuk di-scrape.")
            return []

        print(f"     Ditemukan {len(episodes_to_scrape_nums)} episode baru. Memproses...")
        
        for ep_num in episodes_to_scrape_nums:
            try:
                print(f"        - Memproses Episode: {ep_num}")
                page.locator(f"div.episode-item:has-text('{ep_num}')").first.click(timeout=15000)
                
                iframe_src = None
                page.wait_for_selector("div.player-container iframe", state='attached', timeout=20000)
                all_iframes = page.locator("div.player-container iframe").all()
                for frame in all_iframes:
                    src_attr = frame.get_attribute('src') or ''
                    if 'disqus' not in src_attr and src_attr:
                        iframe_src = src_attr
                        print(f"           Iframe video ditemukan: {iframe_src[:50]}...")
                        break
                
                if iframe_src:
                    # Karena kita tidak memilih bahasa, kita sebut saja 'Default'
                    newly_scraped_episodes.append({
                        "episode_number": ep_num,
                        "sources": [{"language": "Default", "iframe_url": iframe_src}]
                    })
                else:
                    print(f"           Tidak ada iframe video yang valid untuk episode {ep_num}.")

            except Exception as e:
                print(f"        [PERINGATAN] Gagal memproses episode {ep_num}: {e}")
                continue # Lanjut ke episode berikutnya
                
    except Exception as e:
        print(f"     [ERROR] Gagal memuat halaman episode. Melewati anime ini. Detail: {e}")

    return newly_scraped_episodes

def main():
    db_shows = load_database()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        page = context.new_page()

        shows_on_main_page = scrape_main_page_shows(page)

        if not shows_on_main_page:
            print("Tidak ada anime yang ditemukan di halaman utama. Selesai.")
            browser.close()
            return
        
        print("\n=== TAHAP 2: MEMPROSES SETIAP ANIME ===")
        for show_summary in shows_on_main_page:
            show_key = show_summary['metadata_url']
            
            # Jika anime benar-benar baru
            if show_key not in db_shows:
                print(f"\nMemproses anime baru: '{show_summary['title']}'")
                metadata = scrape_show_metadata(page, show_summary['metadata_url'])
                new_episodes = scrape_show_episodes(page, show_summary['episode_page_url'], existing_episode_numbers=set())
                
                db_shows[show_key] = {
                    **show_summary,
                    **metadata,
                    "episodes": new_episodes
                }
            # Jika anime sudah ada di database
            else:
                print(f"\nMengecek update untuk: '{show_summary['title']}'")
                existing_ep_numbers = {ep['episode_number'] for ep in db_shows[show_key].get('episodes', [])}
                newly_found_episodes = scrape_show_episodes(page, show_summary['episode_page_url'], existing_ep_numbers)

                if newly_found_episodes:
                    db_shows[show_key]['episodes'].extend(newly_found_episodes)
                    # Urutkan kembali daftar episode untuk konsistensi
                    db_shows[show_key]['episodes'].sort(key=lambda x: int(''.join(filter(str.isdigit, x.get('episode_number', '0').split()[-1])) or 0))

            # Simpan progres setelah setiap anime diproses
            save_database(db_shows)

        page.close()
        browser.close()
        print("\n=== SEMUA PROSES SELESAI ===")

if __name__ == "__main__":
    main()
