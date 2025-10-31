# scraper.py (Advanced & Efficient Version)

from playwright.sync_api import sync_playwright, TimeoutError
import json
import time
import os

# --- KONFIGURASI ---
DATABASE_FILE = "anime_database.json"

def load_database():
    """Memuat database anime yang sudah ada dari file JSON."""
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r', encoding='utf-8') as f:
            print(f"Database '{DATABASE_FILE}' ditemukan dan dimuat.")
            return json.load(f)
    print(f"Database '{DATABASE_FILE}' tidak ditemukan. Akan membuat yang baru.")
    return []

def save_database(data):
    """Menyimpan data anime ke file JSON."""
    with open(DATABASE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"Database berhasil disimpan ke '{DATABASE_FILE}'.")

def scrape_main_page_shows(page):
    """Tahap 1: Scrape daftar anime terbaru dari halaman utama."""
    url = "https://kickass-anime.ru/"
    print("\n=== TAHAP 1: MENGAMBIL DAFTAR ANIME DARI HALAMAN UTAMA ===")
    
    try:
        page.goto(url, timeout=90000, wait_until="domcontentloaded")
        page.wait_for_selector('div.latest-update div.show-item', timeout=60000)
        
        last_height = page.evaluate("document.body.scrollHeight")
        while True:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2) # Waktu tunggu scroll bisa lebih singkat
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
    """Mengambil metadata detail (sinopsis, genre, dll.) dari halaman anime."""
    print(f"   - Mengambil metadata dari: {show_url}")
    try:
        page.goto(show_url, timeout=90000, wait_until="domcontentloaded")
        
        # Ambil poster, sinopsis, dan genre
        poster_url = page.locator("div.banner-section div.v-image__image").get_attribute("style").split('url("')[1].split('")')[0]
        synopsis = page.locator("div.v-card__text div.text-caption").inner_text()
        genres = [genre.inner_text() for genre in page.locator("div.v-card__text span.v-chip__content").all()]

        # Ambil tahun dan tipe dari bagian info
        info_elements = page.locator("div.d-flex.mt-2.mb-3 div.text-subtitle-2").all()
        year = info_elements[2].inner_text() if len(info_elements) > 2 else "N/A"
        show_type = info_elements[0].inner_text() if len(info_elements) > 0 else "N/A"

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

def scrape_episodes_for_show(page):
    """
    Mengambil semua episode dari semua halaman paginasi.
    """
    episode_item_selector = "div.episode-item"
    page.wait_for_selector(episode_item_selector, timeout=60000)
    
    all_episodes = []
    
    while True:
        # Ambil semua episode di halaman saat ini
        episodes_on_page = page.locator(episode_item_selector).all()
        for ep_element in episodes_on_page:
            ep_num = ep_element.locator("span.v-chip__content").inner_text()
            # Mendapatkan link episode memerlukan navigasi, jadi kita simpan elemennya untuk diklik nanti
            all_episodes.append({'episode_number': ep_num, 'element': ep_element})
            
        # Cek tombol "next page"
        next_button_selector = ".v-select__selections + .v-input__append-inner"
        page_dropdown = page.locator("div.v-card__title .v-select").filter(has_text="Page")
        
        if not page_dropdown.is_visible():
            break

        # Klik dropdown untuk membuka opsi halaman
        page_dropdown.click()
        time.sleep(0.5)
        
        # Cek apakah ada halaman berikutnya
        page_options = page.locator(".v-list-item__title").all()
        current_page_text = page_dropdown.locator(".v-select__selection").inner_text()
        
        next_page_found = False
        for i, option in enumerate(page_options):
            if option.inner_text() == current_page_text and i + 1 < len(page_options):
                print(f"      - Pindah ke halaman episode berikutnya...")
                page_options[i+1].click()
                time.sleep(2) # Tunggu konten baru dimuat
                next_page_found = True
                break
        
        if not next_page_found:
            break # Tidak ada halaman berikutnya

    print(f"   Ditemukan total {len(all_episodes)} episode di semua halaman.")
    return all_episodes

def main():
    db_data = load_database()
    db_shows = {show['show_url']: show for show in db_data}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        main_page = browser.new_page()

        latest_shows_list = scrape_main_page_shows(main_page)
        main_page.close()

        if not latest_shows_list:
            print("Tidak ada anime yang ditemukan. Proses berhenti.")
            browser.close()
            return
        
        print("\n=== TAHAP 2: MEMPROSES SETIAP ANIME DAN EPISODENYA ===")
        for show_summary in latest_shows_list:
            show_url = show_summary['show_url']
            
            # --- Logika Incremental Scraping ---
            if show_url in db_shows:
                print(f"\nAnime '{show_summary['title']}' sudah ada di database. Mengecek pembaruan...")
                # Nanti kita tambahkan logika untuk scrape episode baru saja
                # Untuk sekarang, kita lewati dulu
                # continue 
                pass # Hapus `pass` dan uncomment `continue` untuk efisiensi penuh

            print(f"\nMemproses anime baru: '{show_summary['title']}'")
            page = browser.new_page()

            try:
                # 1. Ambil Metadata
                details = scrape_show_details(page, show_url)
                
                # 2. Klik "Watch Now" dan navigasi
                page.locator("a.pulse-button:has-text('Watch Now')").click()
                
                # 3. Ambil semua elemen episode dari semua halaman
                episode_elements_to_scrape = scrape_episodes_for_show(page)
                
                # 4. "Cicil" dan scrape iframe untuk setiap episode
                scraped_episodes = []
                for i, ep_info in enumerate(episode_elements_to_scrape):
                    print(f"      - Memproses iframe untuk: {ep_info['episode_number']} ({i+1}/{len(episode_elements_to_scrape)})")
                    
                    # Klik elemen episode untuk navigasi
                    is_playing = ep_info['element'].locator("div.v-overlay__content:has-text('Playing')").is_visible()
                    if not is_playing:
                        ep_info['element'].click()
                        # Tunggu iframe baru muncul
                        page.wait_for_function("document.querySelector('div.player-container iframe') !== null", timeout=60000)

                    iframe_src = "Not Found"
                    try:
                        iframe_element = page.locator("div.player-container iframe.player")
                        iframe_element.wait_for(state="visible", timeout=30000)
                        iframe_src = iframe_element.get_attribute('src')
                    except TimeoutError:
                        print(f"        [PERINGATAN] Iframe tidak ditemukan.")

                    scraped_episodes.append({
                        "episode_number": ep_info['episode_number'],
                        "episode_url": page.url,
                        "iframe_url": iframe_src
                    })
                
                # Gabungkan semua data
                final_show_data = {
                    "title": show_summary['title'],
                    "show_url": show_url,
                    **details,
                    "episodes": scraped_episodes
                }
                db_shows[show_url] = final_show_data

            except Exception as e:
                print(f"   [ERROR FATAL] Gagal memproses '{show_summary['title']}'. Melewati. Detail: {e}")
            finally:
                page.close()

        browser.close()
        
        save_database(list(db_shows.values()))
        print("\n=== PROSES SCRAPING SELESAI ===")

if __name__ == "__main__":
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("Error: Library 'beautifulsoup4' tidak ada. Install dengan 'pip install beautifulsoup4'")
        exit()
        
    main()
