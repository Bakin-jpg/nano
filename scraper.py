# scraper.py (Versi Perbaikan)

import json
import time
import os
import re
from playwright.sync_api import sync_playwright, TimeoutError
from bs4 import BeautifulSoup

DATABASE_FILE = "anime_database.json"
PAGINATION_THRESHOLD = 50
EPISODE_BATCH_LIMIT = 10 # Batas cicilan per eksekusi

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
    details = {}
    try:
        page.goto(show_url, timeout=90000)

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
            else:
                print(f"\nMengecek episode untuk: '{show_summary['title']}'")

            page = browser.new_page()
            try:
                page.goto(show_url, timeout=90000)
                page.locator("a.pulse-button:has-text('Watch Now')").click()
                page.wait_for_selector("div.episode-item", timeout=60000)
                
                # Menunggu elemen stabil untuk dijadikan target klik penutup menu
                page.wait_for_selector('div.episode-list-container .v-card__title', timeout=10000)

                try:
                    target_language = "Japanese (Sub)"
                    print(f"   Mengecek dropdown Sub/Dub...")
                    
                    sub_dub_dropdown = page.locator(".v-select").filter(has_text="Sub/Dub")
                    sub_dub_dropdown.wait_for(state="visible", timeout=7000)
                    
                    current_lang = sub_dub_dropdown.locator(".v-select__selection").inner_text()
                    
                    if target_language.lower() in current_lang.lower():
                        print(f"      - '{current_lang}' sudah merupakan pilihan yang benar.")
                    else:
                        print(f"      - Pilihan saat ini '{current_lang}'. Mencoba mengganti...")
                        sub_dub_dropdown.click()
                        page.wait_for_selector(".v-menu__content .v-list-item", state="visible", timeout=5000)
                        
                        target_option = page.locator(f".v-menu__content .v-list-item__title:has-text('{target_language}')")
                        
                        if target_option.is_visible():
                            target_option.click()
                            print(f"      - Mengganti ke '{target_language}'. Menunggu daftar episode dimuat ulang...")
                            page.wait_for_selector(".v-menu__content", state="hidden", timeout=10000)
                            page.wait_for_selector("div.episode-item", state="attached", timeout=10000)
                            print("      - Daftar episode berhasil dimuat ulang.")
                        else:
                            print(f"      - Opsi '{target_language}' tidak tersedia. Menutup dropdown.")
                            page.locator('div.episode-list-container .v-card__title').click() 
                            page.wait_for_selector(".v-menu__content", state="hidden", timeout=10000)

                except TimeoutError:
                    print("   [INFO] Dropdown Sub/Dub tidak ditemukan. Melanjutkan.")
                except Exception as e:
                    print(f"   [PERINGATAN] Terjadi error saat mencoba mengganti sub: {e}")
                
                print("   Memproses daftar halaman...")
                existing_ep_numbers = {ep['episode_number'] for ep in db_shows[show_url].get('episodes', [])}
                episodes_to_process_map = {}
                page_options_texts = ["default"]
                
                # PERBAIKAN UTAMA: Pendekatan yang lebih robust untuk dropdown Page
                try:
                    # Cari dropdown Page dengan cara yang lebih spesifik
                    page_dropdown = page.locator("div.v-card__title .v-select").filter(has_text="Page")
                    
                    if page_dropdown.is_visible():
                        # Pastikan elemen terlihat sebelum diklik
                        page_dropdown.scroll_into_view_if_needed()
                        
                        # Tunggu sebentar sebelum klik
                        time.sleep(0.5)
                        
                        # Klik dropdown
                        page_dropdown.click(timeout=10000)
                        
                        # Tunggu menu muncul dengan timeout lebih lama
                        try:
                            page.wait_for_selector(".v-menu__content", state="visible", timeout=15000)
                            # Tunggu item menu muncul
                            page.wait_for_selector(".v-menu__content .v-list-item__title", state="visible", timeout=10000)
                            
                            # Ambil semua opsi halaman
                            page_options = page.locator(".v-menu__content .v-list-item__title").all()
                            page_options_texts = [opt.inner_text() for opt in page_options]
                            
                            print(f"      - Ditemukan {len(page_options_texts)} opsi halaman")
                        except TimeoutError:
                            print("      [PERINGATAN] Timeout saat menunggu opsi halaman muncul. Menggunakan default.")
                            page_options_texts = ["default"]
                        
                        # Tutup dropdown dengan cara yang lebih aman
                        try:
                            # Coba klik di luar dropdown
                            page.locator('div.episode-list-container .v-card__title').click()
                            page.wait_for_selector(".v-menu__content", state="hidden", timeout=5000)
                        except:
                            # Jika gagal, coba tekan ESC
                            page.keyboard.press('Escape')
                            time.sleep(0.5)
                except Exception as e:
                    print(f"   [PERINGATAN] Error saat memproses dropdown Page: {e}")
                    page_options_texts = ["default"]

                for page_range in page_options_texts:
                    if page_range != "default":
                        # PERBAIKAN: Dapatkan ulang locator di setiap iterasi untuk menghindari stale reference
                        try:
                            current_page_dropdown = page.locator("div.v-card__title .v-select").filter(has_text="Page")
                            if current_page_dropdown.is_visible():
                                current_page_text = current_page_dropdown.locator(".v-select__selection").inner_text()
                                if current_page_text != page_range:
                                    print(f"      - Mengganti ke halaman: {page_range}")
                                    
                                    # Pastikan elemen terlihat
                                    current_page_dropdown.scroll_into_view_if_needed()
                                    time.sleep(0.5)
                                    
                                    # Klik dropdown
                                    current_page_dropdown.click(timeout=10000)
                                    
                                    # Tunggu menu muncul
                                    try:
                                        page.wait_for_selector(".v-menu__content", state="visible", timeout=15000)
                                        page.wait_for_selector(".v-menu__content .v-list-item__title", state="visible", timeout=10000)
                                        
                                        # Klik opsi yang diinginkan
                                        page.locator(f".v-menu__content .v-list-item__title:has-text('{page_range}')").click()
                                        page.wait_for_selector(".v-menu__content", state="hidden", timeout=10000)
                                        page.wait_for_selector("div.episode-item", state="attached", timeout=10000)
                                        time.sleep(0.5)
                                    except TimeoutError:
                                        print(f"      [PERINGATAN] Timeout saat mengganti ke halaman {page_range}")
                                        # Coba tutup menu dan lanjutkan
                                        try:
                                            page.keyboard.press('Escape')
                                            time.sleep(0.5)
                                        except:
                                            pass
                        except Exception as e:
                            print(f"      [PERINGATAN] Error saat navigasi halaman: {e}")

                    # Proses episode di halaman ini
                    try:
                        episode_items = page.locator("div.episode-item").all()
                        for ep_element in episode_items:
                            try:
                                ep_num = ep_element.locator("span.v-chip__content").inner_text()
                                if ep_num not in existing_ep_numbers:
                                    episodes_to_process_map[ep_num] = page_range
                            except:
                                continue
                    except Exception as e:
                        print(f"      [PERINGATAN] Error saat mengambil episode: {e}")

                if not episodes_to_process_map:
                    print("   Tidak ada episode baru untuk di-scrape.")
                    page.close()
                    continue

                episodes_to_scrape = sorted(list(episodes_to_process_map.keys()), key=lambda x: int(''.join(filter(str.isdigit, x.split()[-1])) or 0))

                print(f"   Ditemukan {len(episodes_to_scrape)} episode baru untuk diproses.")
                if len(episodes_to_scrape) > EPISODE_BATCH_LIMIT:
                     print(f"   Akan memproses {EPISODE_BATCH_LIMIT} episode saja (cicilan).")
                     episodes_to_scrape = episodes_to_scrape[:EPISODE_BATCH_LIMIT]

                for i, ep_num in enumerate(episodes_to_scrape):
                    print(f"      - Memproses iframe: {ep_num} ({i+1}/{len(episodes_to_scrape)})")
                    try:
                        target_page_range = episodes_to_process_map[ep_num]
                        # PERBAIKAN: Dapatkan ulang locator sebelum digunakan
                        try:
                            current_page_dropdown_nav = page.locator("div.v-card__title .v-select").filter(has_text="Page")
                            if current_page_dropdown_nav.is_visible():
                                current_page_text = current_page_dropdown_nav.locator(".v-select__selection").inner_text()
                                if target_page_range != "default" and target_page_range != current_page_text:
                                    print(f"         Navigasi ke halaman '{target_page_range}'...")
                                    
                                    # Pastikan elemen terlihat
                                    current_page_dropdown_nav.scroll_into_view_if_needed()
                                    time.sleep(0.5)
                                    
                                    # Klik dropdown
                                    current_page_dropdown_nav.click(timeout=10000)
                                    
                                    # Tunggu menu muncul
                                    try:
                                        page.wait_for_selector(".v-menu__content", state="visible", timeout=15000)
                                        page.wait_for_selector(".v-menu__content .v-list-item__title", state="visible", timeout=10000)
                                        
                                        # Klik opsi yang diinginkan
                                        page.locator(f".v-menu__content .v-list-item__title:has-text('{target_page_range}')").click()
                                        page.wait_for_selector(".v-menu__content", state="hidden", timeout=10000)
                                        page.wait_for_selector("div.episode-item", state="attached", timeout=10000)
                                        time.sleep(0.5)
                                    except TimeoutError:
                                        print(f"         [PERINGATAN] Timeout saat navigasi ke halaman {target_page_range}")
                                        # Coba tutup menu dan lanjutkan
                                        try:
                                            page.keyboard.press('Escape')
                                            time.sleep(0.5)
                                        except:
                                            pass
                        except Exception as e:
                            print(f"         [PERINGATAN] Error saat navigasi: {e}")

                        # Klik episode
                        ep_element = page.locator(f"div.episode-item:has-text('{ep_num}')").first
                        ep_element.click(timeout=15000)

                        # Tunggu iframe muncul
                        page.wait_for_selector("div.player-container iframe", state='attached', timeout=90000)
                        iframe_element = page.locator("div.player-container iframe.player")
                        iframe_element.wait_for(state="visible", timeout=30000)
                        iframe_src = iframe_element.get_attribute('src')

                        # Simpan data episode
                        db_shows[show_url]['episodes'].append({
                            "episode_number": ep_num, "episode_url": page.url, "iframe_url": iframe_src
                        })
                    except Exception as e:
                        print(f"        [PERINGATAN] Gagal memproses iframe untuk {ep_num}: {e}")

                # Urutkan episode
                db_shows[show_url]['episodes'].sort(key=lambda x: int(''.join(filter(str.isdigit, x.get('episode_number', '0').split()[-1])) or 0))

            except Exception as e:
                print(f"   [ERROR FATAL] Gagal memproses episode untuk '{show_summary['title']}'. Melewati. Detail: {e}")
            finally:
                if not page.is_closed():
                    page.close()

        browser.close()
        save_database(db_shows)

if __name__ == "__main__":
    main()
