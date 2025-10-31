# scraper.py (Perbaikan untuk Lingkungan Server/Headless)

import json
import time
import os
import re
from playwright.sync_api import sync_playwright, TimeoutError
from bs4 import BeautifulSoup

DATABASE_FILE = "anime_database.json"
PAGINATION_THRESHOLD = 50
EPISODE_BATCH_LIMIT = 10

def load_database():
    if os.path.exists(DATABASE_FILE):
        try:
            with open(DATABASE_FILE, 'r', encoding='utf-8') as f:
                print(f"Database '{DATABASE_FILE}' ditemukan dan dimuat.")
                return {show['show_url']: show for show in json.load(f)}
        except json.JSONDecodeError:
            print(f"[PERINGATAN] File database '{DATABASE_FILE}' rusak. Memulai dari awal.")
            return {}
    print(f"Database '{DATABASE_FILE}' tidak ditemukan. Akan membuat yang baru.")
    return {}

def save_database(data_dict):
    # Mengonversi dict kembali ke list sebelum menyimpan
    data_list = list(data_dict.values())
    sorted_data = sorted(data_list, key=lambda x: x.get('title', ''))
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
    details = {}
    try:
        page.goto(show_url, timeout=90000)
        page.wait_for_load_state('networkidle')
        details["poster_image_url"] = page.locator("div.banner-section div.v-image__image").first.get_attribute("style").split('url("')[1].split('")')[0]
        details["synopsis"] = page.locator("div.v-card__text div.text-caption").inner_text(timeout=5000)
        details["genres"] = [g.inner_text() for g in page.locator(".anime-info-card .v-card__text span.v-chip__content").all()]
        info_texts = [info.inner_text() for info in page.locator(".anime-info-card .d-flex.mt-2.mb-3 div.text-subtitle-2").all()]
        details["type"] = next((text for text in info_texts if text in ["TV", "Movie", "OVA", "ONA", "Special"]), "N/A")
        details["year"] = next((text for text in info_texts if re.match(r'^\d{4}$', text)), "N/A")
        print("     Metadata berhasil diambil.")
    except Exception as e:
        print(f"     [PERINGATAN] Gagal mengambil sebagian atau semua metadata: {e}")
    return details

def get_available_languages(page, language_dropdown):
    print("   Dropdown Sub/Dub ditemukan.")
    try:
        language_dropdown.click(timeout=10000)
        page.wait_for_selector("div.v-menu__content", state="visible", timeout=10000)
        time.sleep(1) # Beri waktu untuk render
        
        all_lang_texts = [opt.inner_text() for opt in page.locator("div.v-menu__content .v-list-item__title").all()]
        
        # Klik di tempat lain untuk menutup dropdown, lebih andal daripada Escape
        page.locator("h1.text-h5").click()
        page.wait_for_selector("div.v-menu__content", state="hidden", timeout=10000)

        lang_keywords = ['japanese', 'english', 'chinese']
        available_languages = [lang for lang in all_lang_texts if any(key in lang.lower() for key in lang_keywords)]
        
        if not available_languages:
            return ["Default"]
        return available_languages
    except Exception as e:
        print(f"     [PERINGATAN] Gagal mendapatkan daftar bahasa. Menggunakan 'Default'. Error: {e}")
        # Jika gagal, coba tekan escape untuk memulihkan diri
        page.keyboard.press("Escape")
        return ["Default"]

def change_language(page, language_dropdown, target_lang):
    try:
        current_lang = language_dropdown.locator(".v-select__selection").inner_text(timeout=5000)
        if target_lang.strip().lower() in current_lang.strip().lower():
            return True # Bahasa sudah sesuai

        print(f"           Mengubah bahasa ke '{target_lang}'...")
        language_dropdown.click(timeout=10000)
        page.wait_for_selector("div.v-menu__content[role='menu']", state="visible", timeout=10000)
        time.sleep(1) # Beri waktu untuk render

        option_to_click = page.locator(f"div.v-menu__content .v-list-item__title:has-text('{target_lang}')").first
        option_to_click.click(timeout=10000)
        
        # DIHAPUS: Baris ini adalah penyebab utama timeout.
        # page.wait_for_selector("div.v-menu__content[role='menu']", state="hidden", timeout=10000)
        
        # DITAMBAH: Tunggu hingga loading spinner hilang atau beri jeda
        page.wait_for_selector("div.v-progress-circular", state="hidden", timeout=15000)
        time.sleep(2) # Beri jeda tambahan setelah perubahan
        
        print("           Bahasa berhasil diubah.")
        return True
    except Exception as e:
        print(f"           [PERINGATAN] Gagal mengubah bahasa ke '{target_lang}': {e}")
        page.keyboard.press("Escape") # Coba pulihkan
        return False

def main():
    db_shows = load_database()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        # Proses halaman utama di page terpisah
        main_page = context.new_page()
        latest_shows_list = scrape_main_page_shows(main_page)
        main_page.close()

        if not latest_shows_list:
            browser.close()
            return
        
        print("\n=== TAHAP 2: MEMPROSES SETIAP ANIME DAN EPISODENYA ===")
        for show_summary in latest_shows_list:
            show_url = show_summary['show_url']
            
            # Buka page baru untuk setiap anime agar terisolasi
            page = context.new_page()

            try:
                if show_url not in db_shows:
                    print(f"\nMemproses anime baru: '{show_summary['title']}'")
                    details = scrape_show_details(page, show_url)
                    db_shows[show_url] = {**show_summary, **details, "episodes": []}
                else:
                    print(f"\nMengecek episode untuk: '{show_summary['title']}'")
                    if 'episodes' not in db_shows[show_url]:
                        db_shows[show_url]['episodes'] = []

                page.goto(show_url, timeout=90000)
                page.locator("a.pulse-button:has-text('Watch Now')").click()
                page.wait_for_selector("div.episode-item", timeout=60000)

                language_dropdown = page.locator("div.v-card__title .v-select").filter(has_text=re.compile("sub|dub", re.IGNORECASE))
                available_languages = ["Default"]
                
                if language_dropdown.is_visible(timeout=5000):
                    available_languages = get_available_languages(page, language_dropdown)
                
                print(f"   Akan memproses bahasa: {available_languages}")
                
                all_episodes_map = {}
                for ep_element in page.locator("div.episode-item").all():
                    ep_num = ep_element.locator("span.v-chip__content").inner_text()
                    all_episodes_map[ep_num] = "default"

                existing_episodes_db = {ep['episode_number']: ep for ep in db_shows[show_url].get('episodes', [])}
                episodes_to_scrape_nums = sorted(
                    [ep_num for ep_num in all_episodes_map.keys() if ep_num not in existing_episodes_db],
                    key=lambda x: int(''.join(filter(str.isdigit, x.split()[-1])) or 0)
                )

                if not episodes_to_scrape_nums:
                    print("   Tidak ada episode baru untuk di-scrape.")
                    continue

                print(f"   Ditemukan {len(episodes_to_scrape_nums)} episode baru.")
                
                for ep_num in episodes_to_scrape_nums:
                    print(f"      - Memproses Episode: {ep_num}")
                    episode_data = {"episode_number": ep_num, "sources": []}
                    
                    try:
                        # Klik episode terlebih dahulu
                        page.locator(f"div.episode-item:has-text('{ep_num}')").first.click(timeout=15000)
                        page.wait_for_selector("div.player-container", timeout=15000)
                        time.sleep(1)
                    except Exception as e:
                        print(f"      [PERINGATAN] Gagal mengklik episode {ep_num}. Melewati. Error: {e}")
                        continue
                    
                    for lang_option in available_languages:
                        print(f"         - Mencoba bahasa: '{lang_option}'")
                        
                        if lang_option != "Default" and language_dropdown.is_visible():
                            change_language(page, language_dropdown, lang_option)

                        iframe_src = None
                        try:
                            # Tunggu iframe untuk muncul setelah klik/ganti bahasa
                            page.wait_for_selector("div.player-container iframe", state='attached', timeout=20000)
                            all_iframes = page.locator("div.player-container iframe").all()
                            for frame in all_iframes:
                                src_attr = frame.get_attribute('src') or ''
                                if 'disqus' not in src_attr and src_attr:
                                    iframe_src = src_attr
                                    print(f"           Iframe video ditemukan: {iframe_src[:50]}...")
                                    break
                        except TimeoutError:
                            print("           Tidak ada iframe yang muncul dalam waktu yang ditentukan.")
                        
                        if iframe_src:
                            episode_data["sources"].append({"language": lang_option, "iframe_url": iframe_src})
                        else:
                            print("           Tidak ada iframe video yang valid untuk bahasa ini.")

                    if episode_data["sources"]:
                        db_shows[show_url]['episodes'].append(episode_data)
                
                db_shows[show_url]['episodes'].sort(key=lambda x: int(''.join(filter(str.isdigit, x.get('episode_number', '0').split()[-1])) or 0))

            except Exception as e:
                print(f"   [ERROR FATAL] Gagal memproses episode untuk '{show_summary['title']}'. Melewati. Detail: {e}")
            finally:
                if not page.is_closed():
                    page.close()
                # Simpan database setelah setiap anime selesai diproses
                save_database(db_shows)

        browser.close()
        # Hapus save_database dari sini karena sudah dipindah ke dalam loop
        # save_database(db_shows)

if __name__ == "__main__":
    main()
