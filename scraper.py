# scraper.py (Final Version with Dropdown Pagination Logic)

import json
import time
import os
from playwright.sync_api import sync_playwright, TimeoutError
from bs4 import BeautifulSoup

DATABASE_FILE = "anime_database.json"
EPISODE_BATCH_LIMIT = 20 # Batas cicilan episode untuk anime besar

def load_database():
    if os.path.exists(DATABASE_FILE):
        try:
            with open(DATABASE_FILE, 'r', encoding='utf-8') as f:
                print(f"Database '{DATABASE_FILE}' ditemukan dan dimuat.")
                return {show['show_url']: show for show in json.load(f)}
        except json.JSONDecodeError:
            print(f"[PERINGATAN] Database '{DATABASE_FILE}' rusak. Memulai dari awal.")
            return {}
    print(f"Database '{DATABASE_FILE}' tidak ditemukan. Akan membuat yang baru.")
    return {}

def save_database(data_dict):
    sorted_data = sorted(data_dict.values(), key=lambda x: x.get('title', ''))
    with open(DATABASE_FILE, 'w', encoding='utf-8') as f:
        json.dump(sorted_data, f, ensure_ascii=False, indent=4)
    print(f"\nDatabase berhasil disimpan ke '{DATABASE_FILE}'.")

def scrape_main_page_shows(page):
    url = "https://kickass-anime.ru/"
    print("\n=== TAHAP 1: MENGAMBIL DAFTAR ANIME DARI HALAMAN UTAMA ===")
    try:
        page.goto(url, timeout=120000)
        page.wait_for_selector('div.latest-update div.show-item', timeout=60000)
        
        last_height = page.evaluate("document.body.scrollHeight")
        while True:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == last_height: break
            last_height = new_height

        html_content = page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        shows = {}
        for item in soup.find_all('div', class_='show-item'):
            try:
                title_element = item.find('h2', class_='show-title').find('a')
                title = title_element.text.strip()
                show_url = "https://kickass-anime.ru" + title_element['href']
                if show_url not in shows:
                    shows[show_url] = {'title': title, 'show_url': show_url}
            except (AttributeError, IndexError): continue
        
        print(f"Menemukan {len(shows)} anime unik di halaman utama.")
        return list(shows.values())
    except Exception as e:
        print(f"[ERROR di Tahap 1] Gagal mengambil daftar anime: {e}")
        return []

def scrape_show_details(page, show_url):
    print(f"   - Mengambil metadata dari: {show_url}")
    try:
        page.goto(show_url, timeout=90000)
        details = {}
        details["poster_image_url"] = page.locator("div.banner-section div.v-image__image").first.get_attribute("style").split('url("')[1].split('")')[0]
        details["synopsis"] = page.locator("div.v-card__text div.text-caption").inner_text(timeout=5000)
        details["genres"] = [g.inner_text() for g in page.locator(".anime-info-card .v-card__text span.v-chip__content").all()]
        info = page.locator(".anime-info-card .d-flex.mt-2.mb-3 div.text-subtitle-2").all()
        details["type"] = info[0].inner_text() if info else "N/A"
        details["year"] = info[2].inner_text() if len(info) > 2 else "N/A"
        print("     Metadata berhasil diambil.")
        return details
    except Exception as e:
        print(f"     [PERINGATAN] Gagal mengambil metadata detail: {e}")
        return {}

def main():
    db_shows = load_database()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        latest_shows_list = scrape_main_page_shows(page)
        page.close()

        if not latest_shows_list:
            browser.close(); return
        
        print("\n=== TAHAP 2: MEMPROSES SETIAP ANIME DAN EPISODENYA ===")
        for show_summary in latest_shows_list:
            show_url = show_summary['show_url']
            
            if show_url not in db_shows:
                print(f"\nMemproses anime baru: '{show_summary['title']}'")
                page = browser.new_page()
                details = scrape_show_details(page, show_url)
                db_shows[show_url] = {**show_summary, **details, "episodes": []}
                page.close()

            print(f"\nMengecek episode untuk: '{show_summary['title']}'")
            page = browser.new_page()
            try:
                page.goto(show_url, timeout=90000)
                page.locator("a.pulse-button:has-text('Watch Now')").click()
                page.wait_for_selector("div.episode-item", timeout=60000)

                existing_ep_numbers = {ep['episode_number'] for ep in db_shows[show_url].get('episodes', [])}
                episodes_to_process = []

                # --- LOGIKA PAGINASI DROPDOWN BARU ---
                page_dropdown = page.locator("div.v-card__title .v-select").filter(has_text="Page")
                page_dropdown.click()
                time.sleep(1) # Tunggu menu muncul
                page_options = [opt.inner_text() for opt in page.locator(".v-menu__content .v-list-item__title").all()]
                page.keyboard.press("Escape") # Tutup menu
                print(f"   Ditemukan halaman paginasi: {page_options}")

                for page_range in page_options:
                    print(f"   Mengecek halaman: {page_range}")
                    page_dropdown.click()
                    time.sleep(0.5)
                    page.locator(f".v-menu__content .v-list-item__title:has-text('{page_range}')").click()
                    page.wait_for_load_state('domcontentloaded')
                    time.sleep(1.5) # Beri waktu render

                    episodes_on_page = page.locator("div.episode-item").all()
                    for ep_element in episodes_on_page:
                        ep_num = ep_element.locator("span.v-chip__content").inner_text()
                        if ep_num not in existing_ep_numbers:
                            episodes_to_process.append(ep_num)

                if not episodes_to_process:
                    print("   Tidak ada episode baru untuk di-scrape.")
                    continue

                print(f"   Ditemukan {len(episodes_to_process)} episode baru.")
                if len(episodes_to_process) > 20:
                    print(f"   Jumlah episode baru > 20. Akan memproses {EPISODE_BATCH_LIMIT} episode saja (cicilan).")
                    episodes_to_process = episodes_to_process[:EPISODE_BATCH_LIMIT]

                for i, ep_num in enumerate(episodes_to_process):
                    print(f"      - Memproses iframe: {ep_num} ({i+1}/{len(episodes_to_process)})")
                    try:
                        # Pindah ke halaman paginasi yang benar
                        target_page_range = next((pr for pr in page_options if int(pr.split('-')[0]) <= int(''.join(filter(str.isdigit, ep_num))) <= int(pr.split('-')[1])), None)
                        current_page_text = page_dropdown.locator(".v-select__selection").inner_text()
                        if target_page_range and target_page_range != current_page_text:
                            page_dropdown.click(); time.sleep(0.5)
                            page.locator(f".v-menu__content .v-list-item__title:has-text('{target_page_range}')").click()
                            page.wait_for_load_state('domcontentloaded'); time.sleep(1.5)

                        ep_element = page.locator(f"div.episode-item:has-text('{ep_num}')").first
                        ep_element.click()
                        page.wait_for_selector("div.player-container iframe", state='attached', timeout=60000)

                        iframe_element = page.locator("div.player-container iframe.player")
                        iframe_element.wait_for(state="visible", timeout=30000)
                        iframe_src = iframe_element.get_attribute('src')
                        
                        db_shows[show_url]['episodes'].append({
                            "episode_number": ep_num, "episode_url": page.url, "iframe_url": iframe_src
                        })
                    except Exception as e:
                        print(f"        [PERINGATAN] Gagal memproses iframe untuk {ep_num}: {e}")
                
                db_shows[show_url]['episodes'].sort(key=lambda x: int(''.join(filter(str.isdigit, x['episode_number'].split()[-1])) or 0))

            except Exception as e:
                print(f"   [ERROR FATAL] Gagal memproses '{show_summary['title']}'. Melewati. Detail: {e}")
            finally:
                page.close()

        browser.close()
        save_database(db_shows)

if __name__ == "__main__":
    main()
