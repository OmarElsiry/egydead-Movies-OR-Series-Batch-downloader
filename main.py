import os
import sys
import time
import re
import requests
import argparse
from urllib.parse import unquote
from egydead_dl import EgyDeadDL
from playwright.sync_api import sync_playwright


# Force UTF-8 output for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

def resolve_multi_download(url, quality_preference=None):
    """
    Resolves the 'Multi Download' link to get the final direct link.
    Returns: (final_url, selected_quality_name)
    """
    print(f"Resolving Multi Download: {url}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        try:
            # 1. Navigate to the initial redirector
            print("Navigating to initial URL...")
            page.goto(url, timeout=60000)
            page.wait_for_load_state('networkidle')
            print(f"Redirected to: {page.url}")
            
            # 2. Find quality options
            potential_qualities = [
                {"name": "Full HD (1080p)", "selector": "text=Full HD quality"},
                {"name": "HD (720p)", "selector": "text=HD quality"},
                {"name": "SD (480p/360p)", "selector": "text=SD quality"},
                {"name": "Low Quality", "selector": "text=Low quality"},
            ]
            
            found_qualities = []
            for q in potential_qualities:
                if page.locator(q["selector"]).count() > 0:
                    href = page.locator(q["selector"]).get_attribute("href")
                    if href:
                        if not href.startswith("http"):
                            base = "/".join(page.url.split("/")[:3])
                            href = base + href if href.startswith("/") else base + "/" + href
                        found_qualities.append({"name": q["name"], "url": href})

            if not found_qualities:
                print("Could not detect quality options automatically.")
                
                # Check for generic download button
                download_btn = page.locator("text=Download File")
                if download_btn.count() == 0:
                    download_btn = page.locator("text=Create Download Link")
                if download_btn.count() == 0:
                     download_btn = page.locator("button:has-text('Download')")

                if download_btn.count() > 0:
                    print(f"Found download button: {download_btn.first.inner_text()}. Clicking...")
                    try:
                        download_btn.first.click(timeout=5000)
                        page.wait_for_load_state('networkidle')
                    except:
                        print("Click failed or timed out.")
                    
                    for q in potential_qualities:
                        if page.locator(q["selector"]).count() > 0:
                            href = page.locator(q["selector"]).get_attribute("href")
                            if href:
                                if not href.startswith("http"):
                                    base = "/".join(page.url.split("/")[:3])
                                    href = base + href if href.startswith("/") else base + "/" + href
                                found_qualities.append({"name": q["name"], "url": href})
                else:
                    print("No initial download button found.")
                    page.screenshot(path="debug_no_button.png")
                
                if not found_qualities:
                     # Fallback: Construct URLs
                     url_parts = page.url.split('/')
                     file_id = url_parts[-1]
                     base_domain = "/".join(url_parts[:3])
                     
                     manual_qualities = [
                         {"name": "Full HD (Constructed)", "url": f"{base_domain}/f/{file_id}_h"},
                         {"name": "HD (Constructed)", "url": f"{base_domain}/f/{file_id}_n"},
                         {"name": "Original/Default (Constructed)", "url": f"{base_domain}/f/{file_id}"}
                     ]
                     print("Attempting to use constructed quality URLs...")
                     found_qualities.extend(manual_qualities)

            # 3. Fetch sizes
            print("Fetching file sizes for quality options...")
            btn_selector = ".g-recaptcha, a.btn-primary:has-text('Download'), button:has-text('Download'), a:has-text('Download')"
            
            for q in found_qualities:
                try:
                    print(f"Checking {q['name']}...")
                    page.goto(q['url'], timeout=30000)
                    page.wait_for_load_state('networkidle')
                    
                    btn = page.locator(btn_selector).first
                    if btn.count() > 0:
                        text = btn.inner_text()
                        size_match = re.search(r'(\d+(?:\.\d+)?\s*(?:GB|MB|KB))', text, re.IGNORECASE)
                        q['size'] = size_match.group(1) if size_match else "Unknown Size"
                        q['has_button'] = True
                    else:
                        q['size'] = "Button not found"
                        q['has_button'] = False
                except Exception as e:
                    print(f"Error checking {q['name']}: {e}")
                    q['size'] = "Error"
                    q['has_button'] = False

            print("\nAvailable Qualities:")
            valid_qualities = [q for q in found_qualities if q.get('has_button')]
            
            if not valid_qualities:
                print("No valid download buttons found on quality pages.")
                # Fallback: Check original page
                print("Checking original page for download button...")
                try:
                    if 'url_parts' in locals():
                         original_url = f"{base_domain}/{file_id}"
                         print(f"Navigating back to: {original_url}")
                         page.goto(original_url, timeout=30000)
                         page.wait_for_load_state('networkidle')
                         
                         btn = page.locator(btn_selector).first
                         if btn.count() > 0:
                             print("Found button on original page!")
                             valid_qualities.append({
                                 "name": "Single Quality / Direct",
                                 "url": original_url,
                                 "size": "Unknown", 
                                 "has_button": True
                             })
                         else:
                             page.screenshot(path="debug_fallback_fail.png")
                except Exception as e:
                    print(f"Fallback failed: {e}")

            if not valid_qualities:
                 return None, None

            # 4. Ask user for quality
            selected_q = None
            if len(valid_qualities) == 1:
                selected_q = valid_qualities[0]
            elif quality_preference:
                 for q in valid_qualities:
                    if quality_preference.lower() in q["name"].lower():
                        selected_q = q
                        break
            
            if not selected_q:
                for i, q in enumerate(valid_qualities):
                    print(f"{i+1}. {q['name']} - {q.get('size', 'Unknown')}")
                
                while True:
                    try:
                        choice = int(input("Select quality (number): ")) - 1
                        if 0 <= choice < len(valid_qualities):
                            selected_q = valid_qualities[choice]
                            break
                    except ValueError:
                        pass
                    print("Invalid selection.")

            print(f"Selected: {selected_q['name']} ({selected_q.get('size', 'Unknown')})")
            
            # 5. Navigate and Click
            if page.url != selected_q['url']:
                page.goto(selected_q['url'])
                page.wait_for_load_state('networkidle')
            
            dl_btn = page.locator(btn_selector).first
            if dl_btn.count() > 0:
                print("Found download trigger button. Clicking...")
                dl_btn.click(force=True)
                print("Waiting for final link...")
                time.sleep(10)
                
                all_links = page.eval_on_selector_all("a", "elements => elements.map(e => e.href)")
                for link in all_links:
                    if ".mp4" in link and ("premilkyway" in link or "cdn" in link or len(link) > 100):
                        return link, selected_q['name']
            
        except Exception as e:
            print(f"Error in Playwright: {e}")
        finally:
            browser.close()
            
    return None, None


def download_file(url, folder, filename):
    try:
        print(f"Downloading: {filename}")
        print(f"URL: {url}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://haxloppd.com/' # Generic referer might help
        }
        
        with requests.get(url, stream=True, headers=headers, timeout=30) as r:
            r.raise_for_status()
            
            filepath = os.path.join(folder, filename)
            
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            print("Download complete.")
            return True
    except Exception as e:
        print(f"Download failed: {e}")
        return False

def process_download_item(dl, url, item_name, download_folder, action):
    print(f"\nProcessing: {item_name}...")
    
    links = dl.get_download_links(url)
    
    multi_link = None
    for link in links:
        if "تحميل متعدد" in link['server']:
            multi_link = link
            break
    
    if not multi_link:
        print("No 'Multi Download' server found. Checking alternatives...")
        for link in links:
            if "تحميل" in link['server'] or "Multi" in link['server']:
                multi_link = link
                print(f"Found alternative: {link['server']}")
                break
        
        if not multi_link and links:
             print("Available servers:")
             for i, l in enumerate(links):
                 print(f"{i+1}. {l['server']}")
             
             # Let user choose if no multi link
             try:
                 choice = int(input("Select server (number) or 0 to skip: ")) - 1
                 if choice >= 0 and choice < len(links):
                     multi_link = links[choice]
             except ValueError:
                 pass
                 
             if not multi_link:
                 print("Skipping as no suitable server found.")
                 return

        elif not multi_link:
             print("No links found at all.")
             return
        
    print(f"Found Download link: {multi_link['url']}")
    
    final_url, quality_name = resolve_multi_download(multi_link['url'])
    
    if final_url:
        print(f"Resolved Final URL: {final_url}")
        
        if action == 'link':
            print(f"\n[DIRECT LINK] {item_name} ({quality_name}):\n{final_url}\n")
            return

        safe_q_name = quality_name.replace(' (Constructed)', '').replace(' ', '_')
        # Sanitize filename
        safe_item_name = re.sub(r'[\\/*?:"<>|]', "", item_name).replace(' ', '_')
        filename = f"{safe_item_name}_{safe_q_name}.mp4"
        download_file(final_url, download_folder, filename)
    else:
        print("Failed to resolve final download link.")

def main():
    parser = argparse.ArgumentParser(description="EgyDead Downloader")
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--mode", choices=["movie", "series"], help="Content type")
    parser.add_argument("--action", choices=["download", "link"], help="Action to perform")
    args = parser.parse_args()

    # 1. Get Mode
    if args.mode:
        mode = args.mode
    else:
        print("\nSelect Mode:")
        print("1. Movie")
        print("2. Series")
        while True:
            try:
                choice = int(input("Selection: "))
                if choice == 1:
                    mode = "movie"
                    break
                elif choice == 2:
                    mode = "series"
                    break
            except ValueError:
                pass
            print("Invalid selection.")

    # 2. Get Action
    if args.action:
        action = args.action
    else:
        print("\nSelect Action:")
        print("1. Download File")
        print("2. Get Direct Link Only")
        while True:
            try:
                choice = int(input("Selection: "))
                if choice == 1:
                    action = "download"
                    break
                elif choice == 2:
                    action = "link"
                    break
            except ValueError:
                pass
            print("Invalid selection.")

    # 3. Get Query
    if args.query:
        query = args.query
    else:
        query = input("Enter search query: ").strip()
        if not query:
            print("Query cannot be empty.")
            return

    dl = EgyDeadDL()
    print(f"\nSearching for '{query}'...")
    results = dl.search(query)
    
    if not results:
        print("No results found.")
        return

    # 4. Select Content
    print("\nSelect Content:")
    for i, res in enumerate(results):
        print(f"{i+1}. {res['title']}")
    
    selected_page = None
    while True:
        try:
            choice = int(input("Selection: ")) - 1
            if 0 <= choice < len(results):
                selected_page = results[choice]
                break
        except ValueError:
            pass
        print("Invalid selection.")

    print(f"Selected: {selected_page['title']}")
    
    download_folder = os.path.join("downloaded", query.replace(" ", "_"))
    if action == "download":
        os.makedirs(download_folder, exist_ok=True)

    # 5. Process based on Mode
    if mode == "movie":
        print("Fetching content details...")
        resp = requests.get(selected_page['url'], headers=dl.headers)
        
        # Check if it's a collection (e.g. "Series of films...")
        # Often collections list movies similarly to episodes or related items
        # We look for links that look like movie pages inside this page
        
        # Heuristic: Look for links that are NOT episodes but are internal content links
        # This regex looks for links that might be movies in a collection
        # Adjust regex based on actual site structure if needed. 
        # Assuming movie links are like the search result links.
        
        # Try to find "sub-items" which could be movies in a collection
        # Structure: <li class="movieItem"><a href="..." title="...">
        sub_links = re.findall(r'<li class="movieItem">\s*<a href="([^"]+)" title="([^"]+)"', resp.text)
        
        if not sub_links:
             # Try another common pattern for lists
             sub_links = re.findall(r'<a href="([^"]+)"[^>]*class="[^"]*BlockItem[^"]*"[^>]*>(.*?)</a>', resp.text, re.DOTALL)

        # Clean up found links
        cleaned_sub_items = []
        for link, title_or_html in sub_links:
             # If the second group is HTML (from the fallback regex), extract title
             if "<" in title_or_html:
                 title_match = re.search(r'alt="([^"]+)"', title_or_html)
                 title = title_match.group(1) if title_match else "Unknown Title"
             else:
                 title = title_or_html

             if "Episode" not in link and "/episode/" not in link:
                 cleaned_sub_items.append({'url': link, 'title': title})

        if cleaned_sub_items:
            print(f"\nFound {len(cleaned_sub_items)} items in this collection:")
            for i, item in enumerate(cleaned_sub_items):
                print(f"{i+1}. {item['title']}")
            
            print("Select item to download (or 0 for all):")
            try:
                choice = int(input("Selection: "))
                if choice == 0:
                    for item in cleaned_sub_items:
                         process_download_item(dl, item['url'], item['title'], download_folder, action)
                elif 0 < choice <= len(cleaned_sub_items):
                    item = cleaned_sub_items[choice-1]
                    process_download_item(dl, item['url'], item['title'], download_folder, action)
                else:
                    print("Invalid selection.")
            except ValueError:
                print("Invalid input.")
        else:
            # Treat as single movie
            process_download_item(dl, selected_page['url'], selected_page['title'], download_folder, action)
    
    elif mode == "series":
        print("Fetching episodes...")
        resp = requests.get(selected_page['url'], headers=dl.headers)
        
        # Try to find episodes
        episode_links = re.findall(r'href="([^"]*/episode/[^"]+)"', resp.text)
        episode_links = [link for link in list(set(episode_links)) if not link.endswith("/episode/")]
        
        def get_ep_num(url):
            match = re.search(r'episode-(\d+)', url)
            return int(match.group(1)) if match else 0
        
        episode_links.sort(key=get_ep_num)
        
        if not episode_links:
            print("No episodes found. It might be a movie or the structure is different.")
            return

        print(f"Found {len(episode_links)} episodes.")
        print("Enter episode number(s) (e.g. '1', '1-5', 'all'):")
        ep_input = input("> ").strip()
        
        selected_indices = []
        if ep_input.lower() == 'all':
            selected_indices = range(len(episode_links))
        elif '-' in ep_input:
            start, end = map(int, ep_input.split('-'))
            selected_indices = range(start-1, end)
        else:
            try:
                selected_indices = [int(ep_input) - 1]
            except:
                print("Invalid input.")
                return

        for idx in selected_indices:
            if idx < 0 or idx >= len(episode_links):
                continue
                
            ep_url = episode_links[idx]
            ep_num = get_ep_num(ep_url)
            if ep_num == 0:
                ep_num = idx + 1
                
            item_name = f"{selected_page['title']}_Ep{ep_num}"
            process_download_item(dl, ep_url, item_name, download_folder, action)

if __name__ == "__main__":
    main()
