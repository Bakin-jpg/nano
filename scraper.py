# scraper.py

from playwright.sync_api import sync_playwright, TimeoutError
import json
import time

def scrape_kickass_anime(page):
    """
    Tahap 1: Scrape daftar anime terbaru dari halaman utama.
    Menerima 'page' object yang sudah ada agar tidak membuat browser baru.
    """
    url = "https://kickass-anime.ru/"
    print("=== TAHAP 1: MENGAMBIL DAFTAR ANIME DARI HALAMAN UTAMA ===")
    
    try:
        print(f"Mengambil data dari: {url}")
        page.goto(url, timeout=90000, wait_until="domcontentloaded")
        
        print("Menunggu konten awal dimuat...")
        page.wait_for_selector('div.latest-update div.show-item', timeout=60000)
        print("Konten awal ditemukan. Memulai proses scrolling...")

        last_height = page.evaluate("document.body.scrollHeight")
        while True:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            print("   Scroll ke bawah...")
            time.sleep(3)
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                print("   Telah mencapai bagian bawah halaman.")
                break
            last_height = new_height

        print("Mengambil seluruh konten HTML setelah di-scroll...")
        html_content = page.content()
        soup = BeautifulSoup(html_content, 'html.parser')

        latest_update_container = soup.find('div', class_='latest-update')
        anime_items = latest_update_container.find_all('div', class_='show-item')
        
        scraped_data = []
        print(f"Menemukan {len(anime_items)} item anime.")
        for item in anime_items:
            try:
                title_element = item.find('h2', class_='show-title').find('a')
                title = title_element.text.strip()
                show_url = "https://kickass-anime.ru" + title_element['href']
                poster_div = item.find('div', class_='v-image__image--cover')
                poster_url = poster_div['style'].split('url("')[1].split('")')[0]
                
                scraped_data.append({
                    'title': title,
                    'show_url': show_url,
                    'poster_image_url': poster_url
                })
            except (AttributeError, IndexError):
                continue
        return scraped_data
    except Exception as e:
        print(f"[ERROR di Tahap 1] Gagal mengambil daftar anime: {e}")
        return []

def scrape_iframes_for_show(show_url, browser):
    """
    Tahap 2: Untuk satu URL anime, scrape semua iframe episodenya.
    Menerima 'browser' object agar bisa membuat page baru yang terisolasi.
    """
    print(f"--- Memproses Anime dari URL: {show_url} ---")
    page = browser.new_page()
    episodes_data = []
    try:
        page.goto(show_url, timeout=90000, wait_until="domcontentloaded")

        watch_now_selector = "a.pulse-button:has-text('Watch Now')"
        page.wait_for_selector(watch_now_selector, timeout=60000)
        page.locator(watch_now_selector).click()

        episode_item_selector = "div.episode-item"
        page.wait_for_selector(episode_item_selector, timeout=60000)
        
        episode_locators = page.locator(episode_item_selector)
        episode_count = episode_locators.count()
        print(f"   Ditemukan {episode_count} episode.")
        
        for i in range(episode_count):
            all_episodes = page.locator(episode_item_selector)
            current_episode_element = all_episodes.nth(i)

            episode_number_text = current_episode_element.locator("span.v-chip__content").inner_text()
            print(f"      - Memproses: {episode_number_text}")

            is_playing = current_episode_element.locator("div.v-overlay__content:has-text('Playing')").is_visible()
            
            if not is_playing:
                current_episode_element.click()
                page.wait_for_function("document.querySelector('div.player-container iframe') !== null", timeout=60000)
            
            episode_url = page.url
            iframe_src = "Not Found"
            try:
                iframe_selector = "div.player-container iframe.player"
                iframe_element = page.locator(iframe_selector)
                iframe_element.wait_for(state="visible", timeout=30000)
                iframe_src = iframe_element.get_attribute('src')
            except TimeoutError:
                print(f"      [PERINGATAN] Iframe tidak ditemukan untuk {episode_number_text}.")

            episodes_data.append({
                "episode_number": episode_number_text,
                "episode_url": episode_url,
                "iframe_url": iframe_src
            })
        return episodes_data
    except Exception as e:
        print(f"   [ERROR] Gagal memproses anime ini. Melewati. Detail: {e}")
        return []
    finally:
        page.close() # Penting: tutup page setelah selesai untuk hemat memori

def main():
    """
    Fungsi utama untuk mengorkestrasi seluruh proses scraping.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Buat satu page untuk Tahap 1
        main_page = browser.new_page()

        # Jalankan Tahap 1
        latest_shows = scrape_kickass_anime(main_page)
        main_page.close() # Tutup page setelah tidak dibutuhkan

        if not latest_shows:
            print("Tidak ada anime yang ditemukan di halaman utama. Proses berhenti.")
            browser.close()
            return

        # Jalankan Tahap 2 untuk setiap anime
        print("\n=== TAHAP 2: MENGAMBIL DETAIL EPISODE UNTUK SETIAP ANIME ===")
        for show in latest_shows:
            show_url = show.get('show_url')
            if show_url:
                episodes = scrape_iframes_for_show(show_url, browser)
                show['episodes'] = episodes
            else:
                show['episodes'] = []

        browser.close()
        print("\n=== PROSES SCRAPING SELESAI ===")
        
        output_filename = "latest_anime_with_episodes.json"
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(latest_shows, f, ensure_ascii=False, indent=4)
        
        print(f"Data lengkap telah disimpan di '{output_filename}'")

if __name__ == "__main__":
    # Import BeautifulSoup di sini agar tidak error jika file dijalankan tanpa bs4 terinstall
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("Error: Library 'BeautifulSoup4' tidak ditemukan. Silakan install dengan 'pip install beautifulsoup4'")
        exit()
        
    main()
