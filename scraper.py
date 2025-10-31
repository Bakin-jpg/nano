# scraper.py (Final, Robust & Efficient Version)

from playwright.sync_api import sync_playwright, TimeoutError
from bs4 import BeautifulSoup
import json
import time
import os

DATABASE_FILE = "anime_database.json"

def load_database():
    """Memuat database anime dari file JSON, dengan penanganan error."""
    if os.path.exists(DATABASE_FILE):
        try:
            with open(DATABASE_FILE, 'r', encoding='utf-8') as f:
                print(f"Database '{DATABASE_FILE}' ditemukan dan dimuat.")
                return json.load(f)
        except json.JSONDecodeError:
            print(f"[PERINGATAN] File database '{DATABASE_FILE}' rusak. Memulai dari awal.")
            return []
    print(f"Database '{DATABASE_FILE}' tidak ditemukan. Akan membuat yang baru.")
    return []

def save_database(data):
    """Menyimpan data anime ke file JSON."""
    # Urutkan anime berdasarkan judul sebelum menyimpan
    sorted_data = sorted(data, key=lambda x: x['title'])
    with open(DATABASE_FILE, 'w', encoding='utf-8') as f:
        json.dump(sorted_data, f, ensure_ascii=False, indent=4)
    print(f"\nDatabase berhasil disimpan ke '{DATABASE_FILE}'.")

def scrape_main_page_shows(page):
    """Tahap 1: Scrape daftar anime terbaru dari halaman utama."""
    url = "https://kickass-anime.ru/"
    print("\n=== TAHAP 1: MENGAMBIL DAFTAR ANIME DARI HALAMAN UTAMA ===")
    try:
        page.goto(url, timeout=120000, wait_until="domcontentloaded")
        page.wait_for_selector('div.latest-update div.show-item', timeout=60000)
        
        last_height = page.evaluate("document.body.scrollHeight")
        while True:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        html_content = page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        anime_items = soup.find_all('div', class_='show-item')
        
        shows = {}
        for item in anime_items:
            try:
                title_element = item.find('h2', class_='show-title').find('a')
                title = title_element.text.strip()
                show_url = "https://kickass-anime.ru" + title_element['href']
                if show_url not in shows:
                    shows[show_url] = {'title': title, 'show_url': show_url}
            except (AttributeError, IndexError):
                continue
        
        print(f"Menemukan {len(shows)} anime unik di halaman utama.")
        return list(shows.values())
    except Exception as e:
        print(f"[ERROR di Tahap 1] Gagal mengambil daftar anime: {e}")
        return []

def scrape_show_details(page, show_url):
    """(FIXED) Mengambil metadata detail dari halaman anime."""
    print(f"   - Mengambil metadata dari: {show_url}")
    try:
        page.goto(show_url, timeout=90000)
        
        poster_locator = page.locator("div.banner-section div.v-image__image").first
        poster_style = poster_locator.get_attribute("style")
        poster_url = poster_style.split('url("')[1].split('")')[0]
        
        synopsis = page.locator("div.v-card__text div.text-caption").inner_text()
        genres = [genre.inner_text() for genre in page.locator(".anime-info-card .v-card__text span.v-chip__content").all()]
        
        info_elements = page.locator(".anime-info-card .d-flex.mt-2.mb-3 div.text-subtitle-2").all()
        show_type = info_elements[0].inner_text() if info_elements else "N/A"
        year = info_elements[2].inner_text() if len(info_elements) > 2 else "N/A"
        
        print("     Metadata berhasil diambil.")
        return {
            "poster_image_url": poster_url,
            "synopsis": synopsis.strip(),
            "genres": genres,
            "year": year,
            "type": show_type
        }
    except Exception as e:
        print(f"     [PERINGATAN] Gagal mengambil metadata detail: {e}")
        return {}

def get_all_episode_numbers(page):
    """(ROBUST) Mengambil semua nomor episode dari semua halaman paginasi."""
    episode_item_selector = "div.episode-item"
    page.wait_for_selector(episode_item_selector, timeout=60000)
    
    all_episode_numbers = set()

    while True:
        current_ep_elements = page.locator(episode_item_selector).all()
        for el in current_ep_elements:
            all_episode_numbers.add(el.locator("span.v-chip__content").inner_text())
        
        page_dropdown = page.locator("div.v-card__title .v-select").filter(has_text="Page")
        if not page_dropdown.is_visible():
            break

        page_dropdown.click()
        time.sleep(0.5)
        
        page_options = page.locator(".v-menu__content .v-list-item__title").all()
        current_page_text = page_dropdown.locator(".v-select__selection").inner_text()
        
        current_index = -1
        for i, option in enumerate(page_options):
            if option.inner_text() == current_page_text:
                current_index = i
                break
        
        if current_index != -1 and current_index + 1 < len(page_options):
            print(f"      - Pindah ke halaman episode berikutnya...")
            page_options[current_index + 1].click()
            # Tunggu hingga dropdown tertutup dan konten baru mungkin mulai dimuat
            page.wait_for_selector(".v-menu__content", state="hidden")
            time.sleep(2) # Beri waktu untuk JS merender ulang
        else:
            page.keyboard.press("Escape") # Tutup dropdown jika tidak ada halaman lagi
            break

    # Urutkan berdasarkan angka
    sorted_ep_numbers = sorted(list(all_episode_numbers), key=lambda x: int(''.join(filter(str.isdigit, x.split()[-1]))))
    print(f"   Ditemukan total {len(sorted_ep_numbers)} episode unik.")
    return sorted_ep_numbers

def main():
    db_data = load_database()
    db_shows = {show['show_url']: show for show in db_data}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        main_page = browser.new_page()

        latest_shows_list = scrape_main_page_shows(main_page)
        main_page.close()

        if not latest_shows_list:
            browser.close()
            return
        
        print("\n=== TAHAP 2: MEMPROSES SETIAP ANIME DAN EPISODENYA ===")
        for show_summary in latest_shows_list:
            show_url = show_summary['show_url']
            
            is_new_show = show_url not in db_shows
            if not is_new_show:
                print(f"\nAnime '{show_summary['title']}' sudah ada. Mengecek pembaruan...")
            else:
                print(f"\nMemproses anime baru: '{show_summary['title']}'")
            
            page = browser.new_page()
            try:
                if is_new_show:
                    details = scrape_show_details(page, show_url)
                    db_shows[show_url] = {**show_summary, **details, "episodes": []}
                
                page.goto(show_url, timeout=90000)
                page.locator("a.pulse-button:has-text('Watch Now')").click()
                
                all_ep_numbers_on_site = get_all_episode_numbers(page)
                
                existing_ep_numbers = {ep['episode_number'] for ep in db_shows[show_url]['episodes']}
                episodes_to_scrape = [num for num in all_ep_numbers_on_site if num not in existing_ep_numbers]
                
                if not episodes_to_scrape:
                    print("   Tidak ada episode baru untuk di-scrape.")
                    continue
                
                print(f"   Ditemukan {len(episodes_to_scrape)} episode baru: {', '.join(episodes_to_scrape[:5])}{'...' if len(episodes_to_scrape) > 5 else ''}")

                # Batas "cicilan" per eksekusi untuk anime dengan banyak episode baru
                EPISODE_BATCH_LIMIT = 10
                if len(episodes_to_scrape) > 20:
                    print(f"   Jumlah episode baru > 20. Akan memproses {EPISODE_BATCH_LIMIT} episode saja kali ini.")
                    episodes_to_scrape = episodes_to_scrape[:EPISODE_BATCH_LIMIT]
                
                for i, ep_num in enumerate(episodes_to_scrape):
                    print(f"      - Memproses iframe: {ep_num} ({i+1}/{len(episodes_to_scrape)})")
                    try:
                        ep_element = page.locator(f"div.episode-item:has-text('{ep_num}')").first
                        if not ep_element.is_visible():
                            print("         Elemen tidak terlihat, scroll dulu...")
                            ep_element.scroll_into_view_if_needed()
                        
                        ep_element.click()
                        page.wait_for_selector("div.player-container iframe", state='attached', timeout=60000)

                        iframe_element = page.locator("div.player-container iframe.player")
                        iframe_element.wait_for(state="visible", timeout=30000)
                        iframe_src = iframe_element.get_attribute('src')
                        
                        db_shows[show_url]['episodes'].append({
                            "episode_number": ep_num,
                            "episode_url": page.url,
                            "iframe_url": iframe_src
                        })
                    except Exception as e:
                        print(f"        [PERINGATAN] Gagal memproses iframe untuk {ep_num}: {e}")
                
                db_shows[show_url]['episodes'].sort(key=lambda x: int(''.join(filter(str.isdigit, x['episode_number'].split()[-1]))))

            except Exception as e:
                print(f"   [ERROR FATAL] Gagal memproses '{show_summary['title']}'. Melewati. Detail: {e}")
            finally:
                page.close()

        browser.close()
        
        save_database(list(db_shows.values()))

if __name__ == "__main__":
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("Error: Library 'beautifulsoup4' tidak ada. Install dengan 'pip install beautifulsoup4'")
        exit()
