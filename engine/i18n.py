"""화면에 보이는 모든 문구(한국어/영어)와 언어 전환 기능.

여기 있는 것은 전부 '글자'다. 동작 로직은 없다.
새 문구를 추가할 때는 반드시 en/ko 양쪽에 같은 키로 넣어야 한다
(한쪽만 넣으면 다른 언어에서 영어로 튀어나온다 - 테스트가 이걸 검사한다).

사용법:
    from i18n import t, set_language
    set_language('ko')
    t('btn_start')                  -> '시작'
    t('url_count', n=3)             -> '3개'   (중괄호 자리에 값이 들어간다)
"""
# ---------------- 다국어 (영어/한국어) ----------------
# 앱 UI 언어는 기본 영어, 환경설정에서 한국어로 바꿀 수 있다.
# 언어 변경은 다음 실행부터 적용된다 (실행 중 위젯을 전부 다시 그리지 않음).
LANG_DISPLAY = {'en': 'English', 'ko': 'Korean'}

STRINGS = {
    'en': {
        'app_subtitle': 'A tool to mirror entire websites',
        'preferences_btn': '⚙ Preferences',
        'btn_start': 'Start',
        'btn_stop': 'Stop',
        'btn_cancel': 'Cancel',
        'btn_save': 'Save',
        'btn_reset_defaults': 'Reset to Defaults',
        'confirm_reset_title': 'Reset all preferences?',
        'confirm_reset_body': (
            'This resets every preference — including saved API keys — back to the '
            'original defaults. This cannot be undone. Continue?'
        ),
        'btn_browse': 'Browse',
        'btn_open_folder': 'Open Result Folder',
        'btn_no': 'No',
        'btn_cancel_shutdown': 'Cancel Schedule',

        'panel_project': 'Project',
        'label_project_name': 'Project Name',
        'label_save_location': 'Save Location',
        'label_action': 'Collection Method',
        'label_urls': 'URLs to download (one per line)',

        'action_1': 'Download web site(s)',
        'action_2': 'Download all sites linked from page',
        'action_3': 'Get individual files',
        'action_4': 'Update existing download',
        'action_5': 'Continue interrupted download',

        'panel_scope': 'Collection Scope',
        'scope_all': 'Entire site (large, but gets everything)',
        'scope_limit': 'Limit scope',
        'depth_label': 'How many link levels to follow',
        'depth_unit': 'levels',
        'depth_presets_label': 'Common values',
        'depth_preset_1': '1 · This page only',
        'depth_preset_3': '3 · Recommended',
        'depth_preset_5': '5',
        'depth_preset_10': '10 · Covers most sites',
        'depth_caption_limited': 'Only follows links up to the level you set. 1 means just this page; higher numbers reach further.',
        'depth_caption_unlimited': (
            "MirrorX0 default: follows links with no limit and downloads every page on the site. "
            "Large sites can take a long time and use a lot of space. Turn on the checkbox above only if you "
            "want to narrow the scope."
        ),
        'label_same_folder': 'Stay in the same folder as the starting address',
        'caption_same_folder': (
            'Only follows links under the same path as your starting URL. e.g. starting at '
            'site.com/book/1234/1 only downloads site.com/book/1234/* — other sections of the same big '
            'site (other books, boards, etc.) are left alone. This is the fix for '
            '"the whole site got pulled in when I only wanted one section."'
        ),
        'label_domain_scope': 'Domain Scope',
        'domain_scope_host': 'Same host only (default)',
        'domain_scope_subdomain': 'Include subdomains',
        'caption_domain_scope': (
            'Same host only never leaves the exact address you gave (e.g. www.site.com stays www.site.com). '
            'Include subdomains also follows other subdomains of the same site (e.g. blog.site.com, shop.site.com).'
        ),

        'panel_files': 'Which files should be downloaded?',
        'filter_images': 'Images (png, gif, jpg, webp, etc.)',
        'filter_style_script': 'Style / Script (css, js)',
        'filter_docs': 'Documents (pdf, doc, xlsx, hwp, etc.)',
        'filter_media': 'Video / Audio (mp4, mp3, avi, etc.)',
        'filter_archive': 'Archives (zip, rar, 7z, etc.)',
        'label_custom_rules': 'Additional rules (optional, advanced)',
        'caption_custom_rules': 'e.g. -*.pdf — add your own +(include)/-(exclude) rules. Can be left blank.',
        'label_applied_rules': 'Rules that will apply',

        'label_advanced_options': 'Advanced Options',
        'hint_tap_row': 'Tap any row below to change it.',
        'btn_done': 'Done',
        'btn_view_log': 'Activity Log',
        'title_log': 'Activity Log',
        'filters_none': 'None',
        'value_off': 'Off',
        'status_ready': 'Ready to start',
        'label_collect_mode': 'Method',

        'panel_power': 'After Completion',
        'power_none': 'Do nothing',
        'power_on_complete': 'Shut down computer when done',
        'power_after_hours': 'Shut down after set time (regardless of completion)',
        'label_hours_until_shutdown': 'Shut down after (hours)',
        'power_caption_after_hours': (
            "Once the time you set has passed, the computer will shut down whether mirroring is finished or "
            "not. Windows' own shutdown notice will appear, and you can cancel any time."
        ),
        'power_caption_on_complete': (
            'Once mirroring finishes normally (including finishing with errors), the computer will shut down '
            'after 1 minute. Pressing "Stop" yourself will cancel the shutdown.'
        ),
        'power_caption_none': 'The computer will not shut down automatically.',

        'panel_progress': 'Progress',
        'label_status': 'Status',
        'status_waiting': 'Waiting',
        'stat_elapsed': 'Elapsed Time',
        'stat_links': 'Links Scanned',
        'stat_files': 'Files Received',
        'stat_bytes': 'Data Received',
        'stat_speed': 'Transfer Speed',
        'stat_errors': 'Errors',
        'panel_log': 'Live Log',
        'job_waiting': 'Waiting (throttled)',
        'job_receiving': 'Receiving files',

        'dialog_browse_folder_title': 'Choose download folder',

        'prefs_title': 'Preferences',
        'prefs_subtitle': "Settings you rarely need to change. Set them once and they'll keep applying.",
        'section_connection': 'Connection',
        'section_speed_time': 'Speed & Time',
        'section_policy': 'Collection Policy',
        'section_network': 'Network',
        'section_language': 'Language',
        'section_basic': 'Basics',
        'section_expert': 'Expert settings',
        'expert_show': 'Show expert settings',
        'expert_hide': 'Hide expert settings',
        'caption_expert': (
            "You rarely need these. Open them only when something is not working - "
            "for example the site keeps blocking you, or downloads are too slow."
        ),
        'caption_expert_hidden_smart': (
            'Smart Crawl uses a real browser, so the connection/speed/policy settings below do not apply here. '
            'They only affect Site Mirroring.'
        ),
        'label_user_agent': 'User-Agent',
        'caption_user_agent': 'Leave blank to use the default.',
        'label_connections': 'Concurrent Connections',
        'caption_connections': 'Lower this if the site keeps blocking you or refusing connections. Default 8.',
        'label_retries': 'Retry Count',
        'caption_retries': 'Raise this on a flaky connection so fewer files are missed. Default 1.',
        'label_timeout': 'Timeout (sec)',
        'caption_timeout': 'Raise this for slow sites that keep timing out. Default 30 seconds.',
        'label_max_rate': 'Max Speed (Byte/s)',
        'caption_max_rate': 'Set a limit so downloading does not hog your internet. 0 = no limit.',
        'label_robots': 'robots.txt Policy',
        'caption_robots': 'Decide whether to respect a site that blocks crawler access.',
        'robots_0': 'Ignore and collect everything',
        'robots_1': 'Follow when possible',
        'robots_2': 'Always follow (recommended)',
        'label_external_links': 'Also fetch one level into linked external sites',
        'caption_external_links': (
            "By default, only the site you specify is downloaded — links leading outside it aren't followed."
        ),
        'label_proxy': 'Proxy (host:port)',
        'caption_proxy': 'Optional. Leave blank to not use a proxy.',
        'label_use_local_cookies': 'Use my browser login',
        'caption_use_local_cookies': (
            'Reuses the login you already have in Chrome/Edge so sites that need signing in still work. '
            'Only cookies for the site you are downloading are used — nothing else is read or saved.'
        ),
        'warn_cookie_lib_missing': (
            "Browser login needs the 'browser_cookie3' package. Install it with: pip install browser_cookie3"
        ),
        'warn_cookie_read_failed': 'Could not read browser cookies: {e}',
        'warn_cookie_none_matched': 'No saved login found in your browser for this site — continuing without it.',
        'log_cookie_exported': 'Using your browser login ({n} cookie(s) for this site).',
        'panel_project_data': 'Which project?',
        'nav_download': 'Site Download',
        'nav_download_desc': 'Save a whole site as files',
        'nav_crawl': 'Crawling',
        'nav_crawl_desc': 'Pull data out as a table',
        'panel_method': 'How to fetch',
        'method_fast_title': 'Fast (normal sites)',
        'method_fast_desc': 'Downloads files directly. Much faster, but pages built with JavaScript may come out blank.',
        'method_browser_title': 'Via browser (JavaScript sites)',
        'method_browser_desc': 'Opens a real browser and saves what actually renders. Slower, but works on React/Vue-style sites.',
        'intent_save': '📁  Save as Files',
        'intent_data': '📊  Extract as Data',
        'caption_intent_save': 'Download a site to your computer as files you can open offline.',
        'caption_intent_data': 'Pull the info you want into a table (CSV/Excel/DB). Pick a tool below.',
        'mode_mirror': 'Site Mirroring',
        'mode_smart': 'Smart Crawl',
        'caption_mode_mirror': 'Downloads the whole site as static files.',
        'caption_mode_smart': 'Renders each page in a real browser first.',
        'panel_smart_options': 'Smart crawl options',
        'label_smart_preset': 'How much do you want?',
        'caption_smart_preset': 'Most people just pick one of these. You can fine-tune later if needed.',
        'preset_page_title': 'Just this page',
        'preset_page_desc': 'Only the address you typed. Fastest.',
        'preset_light_title': 'This site, lightly (recommended)',
        'preset_light_desc': 'Up to 50 pages, following links 2 levels deep.',
        'preset_full_title': 'This site, thoroughly',
        'preset_full_desc': 'Up to 500 pages, 5 levels deep. Takes a while.',
        'preset_custom_title': 'Set it myself',
        'wait_label_networkidle': 'Wait longest — until images/data finish (recommended)',
        'wait_label_load': 'Wait medium — until the page finishes loading',
        'wait_label_domcontentloaded': 'Fastest — as soon as the text appears',
        'label_max_pages': 'Maximum pages',
        'caption_max_pages': 'Stops after this many pages. Each page opens a real browser, so it is slower.',
        'label_follow_depth': 'Follow links',
        'caption_follow_depth': 'How many link hops to follow from the starting address. 1 means the given pages only.',
        'label_wait_until': 'Wait until',
        'caption_wait_until_networkidle': (
            "Waits until the page settles down (network goes quiet). Safest choice - "
            "the default, and right for almost every site."
        ),
        'caption_wait_until_load': (
            "Moves on once the page's basic files (images etc.) have loaded. Faster than "
            "'networkidle', but can miss content that appears later (infinite scroll, etc.)."
        ),
        'caption_wait_until_domcontentloaded': (
            "Moves on as soon as the page structure is up, without waiting for anything else. "
            "Fastest, but likely to miss content that JavaScript draws in afterward."
        ),
        'summary_smart': 'Smart crawl',
        'summary_smart_value': '{pages} pages · depth {depth}',
        'warn_playwright_missing': "Smart crawl needs Playwright. Install it with: pip install playwright",
        'log_smart_started': 'Starting smart crawl…',
        'log_smart_done': 'Smart crawl finished: {n} page(s) saved.',
        'log_data_tools_hint': (
            "Want this as a spreadsheet instead of files? Click '🧰 Data Tools' above to pull out "
            'just the info you need.'
        ),
        'log_smart_failed': 'Smart crawl did not save anything.',
        'stat_pages': 'Pages visited',
        'status_done': 'Done',
        'status_done_errors': 'Done - {n} link(s) could not be fetched',
        'status_stopped': 'Stopped',
        'status_running': 'Working…',
        'caption_project_name': 'Folder name created under the save location.',
        'hint_need_url': 'Enter an address below to start',
        'existing_title': 'Already downloaded',
        'existing_header_complete': 'You already have a copy of this site',
        'existing_header_interrupted': 'A previous download was interrupted',
        'existing_body_complete': (
            'MirrorX0 can compare with what you already have and fetch only what changed — '
            'much faster, and it saves the site some traffic.'
        ),
        'existing_body_interrupted': (
            'The last download for this folder stopped partway. You can pick up where it left off '
            'instead of starting over.'
        ),
        'existing_update': 'Get only what changed',
        'existing_update_desc': 'Recommended. Compares with the existing copy and downloads new or updated files.',
        'existing_resume': 'Continue where it stopped',
        'existing_resume_desc': 'Recommended. Downloads only the files that were never finished.',
        'existing_fresh': 'Download everything again',
        'existing_fresh_desc': 'Ignores the existing copy and fetches the whole site from scratch.',
        'label_language': 'Language',
        'caption_language': 'Restart the app for the language change to take effect.',

        'confirm_title': 'Start mirroring?',
        'confirm_header': 'Start with these settings?',
        'summary_project_name': 'Project Name',
        'summary_save_location': 'Save Location',
        'summary_target_urls': 'Target URLs',
        'summary_action': 'Collection Method',
        'summary_scope': 'Collection Scope',
        'summary_power': 'After Completion',
        'scope_unlimited': 'No limit (entire site)',
        'scope_n_levels': '{depth} levels',
        'power_text_after_hours': 'Shut down after {hours}h',
        'power_text_on_complete': 'Shut down when done',
        'power_text_none': 'None',
        'url_count': '{n} URL(s)',

        'warn_need_url': '[Warning] Please enter at least one URL to download!',
        'warn_need_project_name': '[Warning] Please enter a project name!',
        'error_engine_missing': '[ERROR] Download engine not found: {path}',
        'log_engine_init': 'Starting MirrorX0 download engine...',
        'warn_disk_critical': (
            '[Warning] Not enough free disk space (only {free}MB left) — not starting. '
            'Free up some space and try again.'
        ),
        'warn_disk_low': '[Warning] Disk space is getting low (only {free}MB left). Continuing anyway.',
        'log_project_folder': 'Project folder: {path}',
        'log_command': 'Running command: {cmd}',
        'log_user_stopped': 'Collection was forcibly stopped by the user.',
        'log_success': 'Mirroring completed successfully.',
        'log_done_with_errors': ('Finished. {n} link(s) could not be fetched - these are usually links that are '
                                 'already broken on the site itself (404). What was downloaded is fine.'),
        'log_done_code': 'Mirroring finished (exit code: {code})',
        'log_fatal_error': 'A fatal error occurred: {result}',
        'warn_folder_not_found': '[Warning] Could not find the folder.',
        'log_prefs_saved': 'Preferences saved.',
        'warn_shutdown_schedule_failed': '[Warning] Failed to schedule shutdown: {e}',
        'notice_shutdown_scheduled': '[Notice] {reason} — scheduled to shut down in {mins} min.',
        'notice_shutdown_cancelled': '[Notice] Scheduled shutdown was cancelled.',
        'shutdown_banner_text': '{reason} — computer will shut down in about {mins} min',
        'reason_after_hours': 'Scheduled shutdown after set time',
        'reason_on_complete': 'Scheduled shutdown after mirroring finished',

        'panel_safety': 'Safety Options',
        'safety_pause_enable': 'Pause between requests',
        'safety_pause_caption': (
            'Waits a random amount of time between each request. Slower, but much gentler on the '
            'target site — lowers the chance of getting blocked.'
        ),
        'safety_pause_between': 'Wait between',
        'safety_pause_and': 'and',
        'safety_pause_unit': 'sec',
        'label_smart_pause_enable': 'Pause between pages',
        'caption_smart_pause': (
            "Waits a random amount of time before opening each page. Slower, but lowers the "
            "chance of the site blocking you — worth turning on for a large site."
        ),
        'safety_maxtime_enable': 'Limit total run time',
        'safety_maxtime_label': 'Stop after (hours)',
        'safety_maxtime_caption': 'Mirroring stops automatically once this many hours have passed, finished or not.',
        'safety_maxsize_enable': 'Limit total size',
        'safety_maxsize_label': 'Stop after (MB)',
        'safety_maxsize_caption': 'Mirroring stops automatically once this much data has been downloaded.',
        'safety_hostcontrol_label': 'Give up on slow hosts',
        'hostcontrol_none': "Don't give up",
        'hostcontrol_timeout': 'On timeout',
        'hostcontrol_slow': 'When slow',
        'hostcontrol_both': 'On timeout or when slow',
        'safety_hostcontrol_caption': 'Stops trying a host early if it keeps timing out or responds too slowly.',
        'btn_load_url_file': 'Load from file',
        'dialog_load_url_file_title': 'Choose a text file with one URL per line',
        'log_loaded_urls': '{n} URL(s) loaded from file.',
        'warn_url_file_failed': '[Warning] Could not read the file: {e}',

        'section_advanced': 'Advanced',
        'label_referer': 'Referer header',
        'caption_referer': 'Optional. Sent as the Referer header on every request.',
        'label_lang_header': 'Preferred language header',
        'caption_lang_header': (
            "Sent to sites as the Accept-Language header (e.g. \"ko, en\") — separate from this app's "
            'own display language.'
        ),
        'label_custom_headers': 'Custom HTTP headers',
        'caption_custom_headers': 'One per line, as "Header-Name: value". Leave blank if not needed.',
        'label_cookies_file': 'Cookies file',
        'caption_cookies_file': "Optional. A Netscape-format cookies.txt, useful for sites that need a login.",
        'dialog_cookies_file_title': 'Choose a cookies.txt file',
        'label_link_format': 'Link format in saved pages',
        'link_format_relative': 'Relative (default)',
        'link_format_absolute': 'Absolute',
        'link_format_original': 'Keep original',
        'caption_link_format': 'Leave as is - the default keeps links working even if you move the folder.',
        'label_near_files': 'Also fetch related files just outside the site',
        'caption_near_files': 'Turn on if images just outside your download range are missing.',
        'label_conn_per_sec': 'New connections per second',
        'caption_conn_per_sec': 'Another way to go easier on a site that blocks you. 0 = use the default.',
        'label_warc': 'Also save a WARC archive',
        'caption_warc': 'Writes a standard .warc file alongside the regular mirror, for archival tools.',
        'label_search_index': 'Build a search index',
        'caption_search_index': 'Only useful if you want to search the saved pages by keyword. Off by default.',

        'tab_schedule': 'Smart Crawl',
        'nav_home': 'Home',
        'nav_preferences': 'Preferences',
        'dashboard_greeting': "Here's a quick look at everything MirrorX0 has done.",
        'section_overview': 'Overview',
        'metric_total_projects': 'Total Projects',
        'metric_total_size': 'Total Downloaded',
        'metric_success_rate': 'Success Rate',
        'metric_activity': 'Recent Activity',
        'metric_scheduled': 'Scheduled Jobs',
        'caption_success_rate': '{success} success · {errors} error(s)',
        'panel_recent_previews': 'Recent Downloads',
        'label_no_previews': "Nothing downloaded yet — start a mirror to see it here.",
        'panel_schedule_list': 'Smart Scheduler',
        'caption_schedule_list': (
            'Runs automatically at the time you set, even while MirrorX0 is closed — as long as the '
            'computer is on and you are logged in (a locked screen is fine).'
        ),
        'label_no_jobs': "You haven't set up a smart crawl yet.",
        'btn_new_job': 'New Smart Crawl',
        'summary_schedule_value': '{n} job(s) registered',
        'summary_schedule_none': 'No scheduled jobs',
        'btn_edit_job': 'Edit',
        'btn_delete_job': 'Delete',
        'job_mode_httrack': 'Fast (normal sites)',
        'job_mode_smart': 'Smart (browser-rendered)',
        'job_mode_both': 'Both',
        'schedule_type_once': 'Once',
        'schedule_type_hourly': 'Hourly',
        'schedule_type_daily': 'Daily',
        'schedule_type_weekly': 'Weekly',
        'job_status_never_run': 'Not run yet',
        'job_status_running': 'Running',
        'job_status_success': 'Done',
        'job_status_errors': 'Done with errors',
        'job_status_error': 'Failed',
        'dialog_job_title': 'Scheduled Job',
        'label_job_name': 'Job Name',
        'label_job_mode': 'Crawl Mode',
        'label_schedule_type': 'Repeat',
        'label_schedule_time': 'Time',
        'label_schedule_interval': 'Every (hours) — used for "Hourly"',
        'label_schedule_date': 'Date (YYYY-MM-DD) — used for "Once"',
        'label_schedule_weekdays': 'Days of week — used for "Weekly"',
        'weekday_mon': 'Mon', 'weekday_tue': 'Tue', 'weekday_wed': 'Wed', 'weekday_thu': 'Thu',
        'weekday_fri': 'Fri', 'weekday_sat': 'Sat', 'weekday_sun': 'Sun',
        'caption_schedule_note': (
            'The computer must be on and you must be logged in for this to run — a locked screen is fine.'
        ),
        'warn_job_need_name': '[Warning] Please enter a job name!',
        'warn_job_need_url': '[Warning] Please enter at least one URL!',
        'warn_job_need_date': '[Warning] Please enter a date for a one-time job!',
        'warn_job_invalid_date': '[Warning] Date must be in YYYY-MM-DD format!',
        'log_job_saved': 'Scheduled job saved.',
        'log_job_deleted': 'Scheduled job deleted.',
        'warn_job_schedule_failed': '[Warning] Could not register the scheduled task: {e}',

        'section_ai': 'AI Crawling',
        'label_ai_provider': 'AI Provider',
        'caption_ai_provider': (
            'Which AI is used for field suggestions and data extraction. '
            'Default is Ollama — free and runs on your own PC, but slower. '
            'Enter a cloud API key below to switch to a faster paid provider.'
        ),
        'caption_ollama_tradeoff': (
            'Ollama (free, default): no API key, runs fully on your PC, no per-use cost — but '
            'slower and needs the Ollama app installed (ollama.com) with a model pulled '
            '(e.g. "ollama pull llama3.2"). Anthropic/OpenAI/Gemini (paid): faster and no local '
            'setup, but needs your own API key and costs money per use.'
        ),
        'ollama_status_checking': 'Checking Ollama...',
        'ollama_status_not_installed': "Ollama isn't installed yet. Install it to use the free option.",
        'ollama_status_not_running': "Ollama is installed but not running.",
        'ollama_status_no_model': 'Ollama is running, but no model is downloaded yet.',
        'ollama_status_ready': 'Ollama is ready ({model}).',
        'ollama_status_working': 'Working... this can take a few minutes.',
        'btn_ollama_install': 'Install Ollama',
        'btn_ollama_start': 'Start Ollama',
        'btn_ollama_pull': 'Get Model',
        'btn_ollama_check': 'Check Again',
        'label_api_key_anthropic': 'Anthropic API Key',
        'label_api_key_openai': 'OpenAI API Key',
        'label_api_key_gemini': 'Google Gemini API Key',
        'caption_api_key': (
            'Used for AI-powered data extraction. Stored only on this computer and sent only to the '
            'provider you chose above.'
        ),
        'label_ai_extract_enable': 'Extract data with AI',
        'label_ai_instruction': 'What should be extracted?',
        'caption_ai_instruction': 'Describe what to extract in one sentence.',
        'placeholder_ai_instruction': 'e.g. product name, price, review count',
        'btn_propose_fields': 'Suggest Fields',
        'label_extract_fields': 'Fields to extract',
        'field_col_name': 'Field name',
        'field_col_label': 'Label',
        'field_col_type': 'Type',
        'btn_add_field': '+ Add Field',
        'label_export_formats': 'Export as',
        'btn_run_extraction': 'Run Extraction',
        'dialog_ai_extract_title': 'AI Data Extraction',
        'label_target_folder': 'Target folder',
        'caption_target_folder': 'Pick a folder you already downloaded with "Download Site".',
        'label_save_location': 'Save location',
        'caption_save_location': 'Where the extracted table will be saved.',
        'warn_choose_folder': '[Warning] Please choose a folder first.',
        'dialog_clean_organize_title': 'Make a Tidy Copy',
        'caption_clean_organize_intro': (
            'Creates a tidy copy of a downloaded site, sorted into css/js/images/fonts folders. '
            'The original folder is left untouched.'
        ),
        'btn_run_clean_organize': 'Start Organizing',
        'caption_extract_estimate': (
            'Estimated: about {calls} API call(s) for {files} page(s) '
            '(~{rows} row(s) total). Pattern detection found this for free, without calling the AI.'
        ),
        'btn_ai_extract': 'AI Extract',
        'warn_need_api_key': '[Warning] Please set your Anthropic API key in Preferences first!',
        'warn_need_instruction': '[Warning] Please describe what to extract!',
        'warn_need_sample_page': '[Warning] Could not fetch a sample page to suggest fields from.',
        'warn_propose_failed': '[Warning] Could not suggest fields: {e}',
        'log_fields_proposed': '{n} field(s) suggested.',
        'warn_need_fields': '[Warning] Please add at least one field to extract!',
        'log_ai_extract_started': 'Starting AI extraction...',
        'warn_ai_skip_no_key': '[AI Extraction] Skipped — no API key set.',

        'btn_pagination_extract': 'Extract Paginated List',
        'dialog_pagination_title': 'Extract a Paginated List',
        'caption_pagination_intro': (
            'For listing/catalog pages that continue onto more pages ("Next", "Load more", etc). '
            "No need to mirror the whole site first — just give the starting page's address and the "
            'fields you want, and it will keep following the next page and building one combined table.'
        ),
        'label_pagination_start_url': 'Starting Page Address',
        'label_pagination_max_pages': 'Max pages to follow',
        'warn_pagination_need_url': '[Warning] Please enter the starting page address!',
        'log_pagination_started': 'Starting paginated extraction...',
        'log_pagination_no_rows': '[Paginated Extraction] No rows were extracted.',

        'btn_click_select': 'Point & Click',
        'dialog_click_select_title': 'Point & Click Extraction',
        'caption_click_select_intro': (
            'For pages where automatic detection gets confused (or you just want to be precise). '
            'A real browser window will open — hover over items to highlight them, then click one '
            "example. It'll find every other item that looks structurally the same and turn them "
            'into a table.'
        ),
        'label_click_select_url': 'Page Address',
        'btn_open_browser_pick': 'Open Browser & Pick',
        'status_click_select_waiting': 'Browser window opened — hover an item and click one example...',
        'status_click_select_picked': 'Found {n} similar item(s) (selector: {selector}).',
        'warn_click_select_failed': '[Warning] Could not pick an element: {e}',
        'log_click_select_started': 'Starting point-and-click extraction...',
        'log_click_select_no_rows': '[Point & Click] No rows were extracted.',

        'btn_data_tools': 'Data Tools',
        'dialog_data_tools_title': 'Data Tools',
        'caption_data_tools_intro': (
            'Turn crawled pages into clean, structured data. Pick the one that fits what '
            'you have right now.'
        ),
        'desc_ai_extract': 'Pull just the fields you want out of a mirrored site, into a table.',
        'desc_pagination_extract': 'Follows "Next" through every page and builds one table.',
        'desc_click_select': 'Click one example in a real browser; it finds all similar items.',
        'desc_clean_organize': 'Makes a tidy copy sorted into css/js/images/fonts.',
        'caption_tool_needs_project': 'Needs a completed project (mirror or smart-crawl a site first).',
        'btn_use_tool': 'Use',

        'btn_clean_organize': 'Make a Tidy Copy',
        'log_clean_organize_started': (
            'Creating a tidy copy (assets sorted into css/js/images/fonts, engine '
            "bookkeeping files removed). The original folder is left untouched..."
        ),
        'log_clean_organize_done': 'Tidy copy created: {path}',
        'warn_clean_organize_failed': '[Warning] Could not create a tidy copy: {e}',

        'log_ai_extract_offer_refine': '{n} row(s) extracted. Want to clean up the table in plain English?',
        'dialog_refine_title': 'Clean up the table',
        'caption_refine_intro': (
            "You have {n} row(s). Describe what to change, in your own words — "
            "no formulas needed."
        ),
        'caption_refine_saved_at': 'Saved to: {path}',
        'label_refine_instruction': 'What do you want to change?',
        'caption_refine_examples': (
            'Examples: "drop column B and put column C there instead" · '
            '"fill missing prices with the most common value" · "remove duplicate rows"'
        ),
        'btn_propose_refine': 'Suggest a plan',
        'btn_apply_refine': 'Apply',
        'btn_skip': 'Skip',
        'warn_refine_need_instruction': '[Warning] Please describe what to change first.',
        'warn_refine_failed': '[Warning] Could not get a suggestion: {e}',
        'preview_refine_summary': 'Rows: {rows_before} -> {rows_after}',
        'preview_columns_added': 'Columns added: {cols}',
        'preview_columns_removed': 'Columns removed: {cols}',
        'preview_refine_warnings': 'Skipped: {warnings}',
        'preview_refine_none': "Couldn't find a matching change for that request. Try rephrasing it.",
        'log_refine_applied': 'Cleaned-up table saved ({n} file(s)).',

        'btn_ai_scope_rules': 'AI Rule Suggestions',
        'dialog_ai_scope_title': 'AI Download Scope Rules',
        'label_scope_goal': 'What do you want to download?',
        'caption_scope_goal': 'Describe it in a sentence, e.g. "Only the recipe section, skip login/cart pages".',
        'btn_get_scope_rules': 'Suggest Rules',
        'caption_scope_cost': (
            'Looks at a small sample of links from your starting address(es), then suggests rules with a '
            "single AI call — the cost doesn't grow with site size."
        ),
        'label_proposed_rules': 'Suggested rules (you can edit before applying)',
        'btn_apply_rules': 'Apply',
        'warn_scope_need_goal': '[Warning] Please describe what you want to download!',
        'warn_scope_need_url': '[Warning] Please enter at least one URL first!',
        'log_fetching_link_sample': 'Fetching a link sample...',
        'warn_scope_no_links': '[Warning] Could not find any links to analyze.',
        'warn_scope_failed': '[Warning] Could not get rule suggestions: {e}',
        'log_scope_rules_applied': 'AI-suggested rules applied.',

        'panel_recent_projects': 'Recent Projects',
        'caption_recent_projects': 'Pick up where you left off, or start over from a past project.',
        'label_no_projects': "You haven't mirrored anything yet.",
        'btn_load_project': 'Load',
        'btn_continue_project': 'Continue',
        'btn_delete_project': 'Delete',
        'proj_status_never': 'Not run yet',
        'proj_status_running': 'Running',
        'proj_status_success': 'Done',
        'proj_status_errors': 'Done with errors',
        'proj_status_failed': 'Failed',
        'proj_url_count': '{n} URL(s)',
    },
    'ko': {
        'app_subtitle': '사이트를 통째로 담아두는 도구',
        'preferences_btn': '⚙ 환경설정',
        'btn_start': '시작',
        'btn_stop': '중지',
        'btn_cancel': '취소',
        'btn_save': '저장',
        'btn_reset_defaults': '기본값으로 초기화',
        'confirm_reset_title': '환경설정을 초기화할까요?',
        'confirm_reset_body': (
            '저장된 API 키를 포함한 모든 환경설정이 원래 기본값으로 되돌아갑니다. '
            '되돌릴 수 없습니다. 계속할까요?'
        ),
        'btn_browse': '찾아보기',
        'btn_open_folder': '결과 폴더 열기',
        'btn_no': '아니오',
        'btn_cancel_shutdown': '예약 취소',

        'panel_project': '프로젝트',
        'label_project_name': '프로젝트 이름',
        'label_save_location': '저장 위치',
        'label_action': '수집 방식',
        'label_urls': '받을 주소 (한 줄에 하나씩)',

        'action_1': '웹 사이트 다운로드',
        'action_2': '페이지 안의 모든 사이트 다운로드',
        'action_3': '개별 파일 얻기',
        'action_4': '기존 다운로드 업데이트',
        'action_5': '중단된 다운로드 이어받기',

        'panel_scope': '수집 범위',
        'scope_all': '사이트 모든 범위 (용량은 크지만 모든 자료를 받습니다)',
        'scope_limit': '받아올 범위 제한하기',
        'depth_label': '링크를 몇 단계까지 따라갈지',
        'depth_unit': '단계',
        'depth_presets_label': '자주 쓰는 값',
        'depth_preset_1': '1 · 이 페이지만',
        'depth_preset_3': '3 · 추천',
        'depth_preset_5': '5',
        'depth_preset_10': '10 · 대부분 커버',
        'depth_caption_limited': '입력한 단계까지만 링크를 따라갑니다. 1이면 지금 주소만, 숫자가 클수록 더 멀리까지 받아요.',
        'depth_caption_unlimited': (
            '제한 없이 사이트에 있는 모든 페이지를 링크를 따라가며 받습니다. '
            '사이트가 크면 시간이 오래 걸리고 용량도 커질 수 있어요. 범위를 좁히고 싶을 때만 위 체크박스를 켜세요.'
        ),
        'label_same_folder': '시작 주소와 같은 폴더 안에서만',
        'caption_same_folder': (
            '시작 주소와 같은 경로 아래에 있는 링크만 따라갑니다. 예를 들어 site.com/book/1234/1로 '
            '시작하면 site.com/book/1234/* 만 받고, 같은 큰 사이트 안의 다른 섹션(다른 책, 다른 게시판 등)은 '
            '건드리지 않아요. "한 섹션만 필요한데 사이트 전체가 받아졌다" 문제를 위한 기능이에요.'
        ),
        'label_domain_scope': '도메인 범위',
        'domain_scope_host': '같은 호스트만 (기본)',
        'domain_scope_subdomain': '서브도메인 포함',
        'caption_domain_scope': (
            '같은 호스트만은 지정한 주소를 절대 벗어나지 않습니다 (예: www.site.com이면 계속 www.site.com만). '
            '서브도메인 포함은 같은 사이트의 다른 서브도메인도 따라갑니다 (예: blog.site.com, shop.site.com).'
        ),

        'panel_files': '어떤 파일까지 받을까요?',
        'filter_images': '이미지 (png, gif, jpg, webp 등)',
        'filter_style_script': '스타일 / 스크립트 (css, js)',
        'filter_docs': '문서 (pdf, doc, xlsx, hwp 등)',
        'filter_media': '동영상 / 음악 (mp4, mp3, avi 등)',
        'filter_archive': '압축 파일 (zip, rar, 7z 등)',
        'label_custom_rules': '추가 규칙 (선택, 고급 사용자용)',
        'caption_custom_rules': '예: -*.pdf  처럼 +(포함)/-(제외) 규칙을 직접 추가할 수 있어요. 비워둬도 됩니다.',
        'label_applied_rules': '적용될 규칙',

        'label_advanced_options': '고급 옵션',
        'hint_tap_row': '아래 항목을 누르면 바로 바꿀 수 있어요.',
        'btn_done': '완료',
        'btn_view_log': '작업 로그',
        'title_log': '작업 로그',
        'filters_none': '없음',
        'value_off': '꺼짐',
        'status_ready': '시작할 준비가 됐어요',
        'label_collect_mode': '수집 방식',

        'panel_power': '완료 후 동작',
        'power_none': '아무것도 안 함',
        'power_on_complete': '완료되면 컴퓨터 종료',
        'power_after_hours': '지정한 시간 뒤 컴퓨터 종료 (완료 여부와 상관없이)',
        'label_hours_until_shutdown': '시간 뒤 종료',
        'power_caption_after_hours': (
            '지금부터 입력한 시간이 지나면, 미러링이 끝났든 아니든 컴퓨터를 종료합니다. '
            'Windows 자체 종료 안내가 뜨고, 언제든 취소할 수 있어요.'
        ),
        'power_caption_on_complete': (
            '미러링이 정상적으로 끝나면(오류로 끝나도 포함) 1분 뒤 컴퓨터를 종료합니다. '
            '직접 "강제 중지"를 누르면 종료하지 않습니다.'
        ),
        'power_caption_none': '시작해도 컴퓨터를 자동으로 끄지 않습니다.',

        'panel_progress': '진행 상황',
        'label_status': '상태',
        'status_waiting': '대기 중',
        'stat_elapsed': '경과 시간',
        'stat_links': '스캔한 링크',
        'stat_files': '받은 파일',
        'stat_bytes': '받은 용량',
        'stat_speed': '전송 속도',
        'stat_errors': '오류',
        'panel_log': '실시간 로그',
        'job_waiting': '대기 중 (속도 조절)',
        'job_receiving': '파일 수신 중',

        'dialog_browse_folder_title': '다운로드 폴더 선택',

        'prefs_title': '환경설정',
        'prefs_subtitle': '자주 안 바꿔도 되는 값들이에요. 한 번만 맞춰두면 다음부터 계속 적용됩니다.',
        'section_connection': '연결',
        'section_speed_time': '속도 및 시간',
        'section_policy': '수집 정책',
        'section_network': '네트워크',
        'section_language': '언어',
        'section_basic': '기본',
        'section_expert': '전문가 설정',
        'expert_show': '전문가 설정 펼치기',
        'expert_hide': '전문가 설정 접기',
        'caption_expert': (
            '평소에는 건드릴 일이 없어요. 사이트가 자꾸 막히거나 받는 속도가 너무 느린 것처럼 '
            '문제가 생겼을 때만 열어보세요.'
        ),
        'caption_expert_hidden_smart': (
            '스마트 크롤링은 실제 브라우저로 받기 때문에, 아래 연결·속도·정책 설정이 적용되지 않아요. '
            '그 설정들은 사이트 미러링에만 영향을 줍니다.'
        ),
        'label_user_agent': 'User-Agent',
        'caption_user_agent': '비워두면 기본값을 사용합니다.',
        'label_connections': '동시 연결 수',
        'caption_connections': '사이트가 자꾸 막거나 연결을 거부하면 낮춰보세요. 기본 8.',
        'label_retries': '재시도 횟수',
        'caption_retries': '인터넷이 불안정해 파일이 자꾸 빠지면 올려보세요. 기본 1회.',
        'label_timeout': '타임아웃 (초)',
        'caption_timeout': '느린 사이트에서 자꾸 실패하면 늘려보세요. 기본 30초.',
        'label_max_rate': '최대 속도 (Byte/s)',
        'caption_max_rate': '받는 동안 인터넷이 느려지지 않게 제한을 걸 수 있어요. 0이면 제한 없음.',
        'label_robots': 'robots.txt 정책',
        'caption_robots': '사이트가 크롤러 접근을 막아둔 경우 이를 존중할지 정합니다.',
        'robots_0': '무시하고 전부 수집',
        'robots_1': '가능하면 준수',
        'robots_2': '항상 준수 (권장)',
        'label_external_links': '링크로 연결된 외부 사이트도 1단계 받기',
        'caption_external_links': '기본은 지정한 사이트만 받고, 외부로 나가는 링크는 따라가지 않아요.',
        'label_proxy': '프록시 (host:port)',
        'caption_proxy': '선택사항입니다. 비워두면 프록시를 쓰지 않습니다.',
        'label_use_local_cookies': '내 브라우저 로그인 사용',
        'caption_use_local_cookies': (
            '크롬/엣지에 이미 로그인해 둔 상태를 그대로 써서, 로그인이 필요한 사이트도 받을 수 있어요. '
            '지금 받는 사이트의 쿠키만 사용하고 다른 사이트 것은 읽지도 저장하지도 않아요.'
        ),
        'warn_cookie_lib_missing': (
            "브라우저 로그인 사용에는 'browser_cookie3' 패키지가 필요해요. "
            '설치 명령: pip install browser_cookie3'
        ),
        'warn_cookie_read_failed': '브라우저 쿠키를 읽지 못했어요: {e}',
        'warn_cookie_none_matched': '이 사이트에 대해 브라우저에 저장된 로그인이 없어요 — 로그인 없이 진행합니다.',
        'log_cookie_exported': '브라우저 로그인을 사용합니다 (이 사이트 쿠키 {n}개).',
        'panel_project_data': '어느 프로젝트에서 뽑을까요?',
        'nav_download': '사이트 다운로드',
        'nav_download_desc': '사이트를 통째로 파일로 저장',
        'nav_crawl': '크롤링',
        'nav_crawl_desc': '원하는 데이터를 표로 추출',
        'panel_method': '받는 방식',
        'method_fast_title': '빠르게 (일반 사이트)',
        'method_fast_desc': '파일을 바로 내려받아요. 훨씬 빠르지만, 자바스크립트로 그려지는 페이지는 빈 화면으로 받힐 수 있어요.',
        'method_browser_title': '브라우저로 (JS 사이트)',
        'method_browser_desc': '진짜 브라우저를 열어 화면에 그려진 그대로 저장해요. 느리지만 React/Vue 같은 사이트도 제대로 받아집니다.',
        'intent_save': '📁  파일로 저장',
        'intent_data': '📊  데이터로 뽑기',
        'caption_intent_save': '사이트를 내 컴퓨터에 파일로 받아 오프라인에서 엽니다.',
        'caption_intent_data': '원하는 정보만 표(CSV/엑셀/DB)로 뽑아냅니다. 아래에서 도구를 고르세요.',
        'mode_mirror': '사이트 미러링',
        'mode_smart': '스마트 크롤링',
        'caption_mode_mirror': '사이트를 정적 파일로 통째로 받아요.',
        'caption_mode_smart': '자바스크립트로 그려지는 화면까지 받아요.',
        'panel_smart_options': '스마트 크롤링 옵션',
        'label_smart_preset': '얼마나 받을까요?',
        'caption_smart_preset': '보통은 이 중에서 고르면 됩니다. 필요하면 나중에 세부 조정할 수 있어요.',
        'preset_page_title': '이 페이지만',
        'preset_page_desc': '입력한 주소 한 장만 받아요. 가장 빠릅니다.',
        'preset_light_title': '이 사이트 조금 (권장)',
        'preset_light_desc': '최대 50페이지, 링크를 2단계까지 따라갑니다.',
        'preset_full_title': '이 사이트 넉넉히',
        'preset_full_desc': '최대 500페이지, 5단계까지. 시간이 꽤 걸려요.',
        'preset_custom_title': '직접 설정할래요',
        'wait_label_networkidle': '가장 오래 기다리기 — 이미지·데이터까지 다 뜬 뒤 (권장)',
        'wait_label_load': '보통 — 페이지 로딩이 끝나면',
        'wait_label_domcontentloaded': '가장 빠르게 — 글자가 뜨자마자',
        'label_max_pages': '최대 페이지 수',
        'caption_max_pages': '이 개수만큼 받고 멈춰요. 한 페이지마다 브라우저를 열기 때문에 미러링보다 느립니다.',
        'label_follow_depth': '링크 따라가기',
        'caption_follow_depth': '시작 주소에서 링크를 몇 단계까지 따라갈지 정해요. 1이면 입력한 페이지만 받습니다.',
        'label_wait_until': '대기 조건',
        'caption_wait_until_networkidle': (
            '페이지가 잠잠해질 때까지(네트워크 요청이 뜸해질 때까지) 기다려요. 가장 안전한 기본값이고, '
            '거의 모든 사이트에 이거면 충분해요.'
        ),
        'caption_wait_until_load': (
            "페이지의 기본 자원(이미지 등)이 다 불러와지면 바로 진행해요. 'networkidle'보다 빠르지만, "
            '나중에 나타나는 내용(무한 스크롤 등)은 놓칠 수 있어요.'
        ),
        'caption_wait_until_domcontentloaded': (
            '페이지 뼈대만 갖춰지면 바로 진행해요. 가장 빠르지만, 자바스크립트가 나중에 그려 넣는 '
            '내용은 놓칠 가능성이 커요.'
        ),
        'summary_smart': '스마트 크롤링',
        'summary_smart_value': '{pages}페이지 · 깊이 {depth}',
        'warn_playwright_missing': '스마트 크롤링에는 Playwright가 필요해요. 설치 명령: pip install playwright',
        'log_smart_started': '스마트 크롤링을 시작합니다…',
        'log_smart_done': '스마트 크롤링 완료: {n}개 페이지를 저장했어요.',
        'log_data_tools_hint': (
            '파일 말고 표(데이터)로 뽑고 싶으신가요? 위에 있는 "🧰 데이터 도구"를 눌러 '
            '원하는 정보만 골라내보세요.'
        ),
        'log_smart_failed': '스마트 크롤링이 아무것도 저장하지 못했어요.',
        'stat_pages': '방문한 페이지',
        'status_done': '완료되었어요',
        'status_done_errors': '완료 · 못 받은 링크 {n}개',
        'status_stopped': '중지했어요',
        'status_running': '받는 중…',
        'caption_project_name': '저장 위치 아래에 만들어질 폴더 이름이에요.',
        'hint_need_url': '아래에 받을 주소를 입력하면 시작할 수 있어요',
        'existing_title': '이미 받아둔 게 있어요',
        'existing_header_complete': '이 사이트는 전에 받아둔 게 있어요',
        'existing_header_interrupted': '지난번에 받다가 멈춘 게 있어요',
        'existing_body_complete': (
            '이미 받아둔 것과 비교해서 바뀐 부분만 가져올 수 있어요 — 훨씬 빠르고, '
            '사이트에도 부담을 덜 줍니다.'
        ),
        'existing_body_interrupted': (
            '이 폴더의 지난 다운로드가 중간에 멈췄어요. 처음부터 다시 받지 않고 '
            '멈춘 지점부터 이어받을 수 있어요.'
        ),
        'existing_update': '바뀐 것만 받기',
        'existing_update_desc': '추천. 이미 받아둔 것과 비교해서 새로 생기거나 바뀐 파일만 받아요.',
        'existing_resume': '멈춘 곳부터 이어받기',
        'existing_resume_desc': '추천. 아직 못 받은 파일만 받아요.',
        'existing_fresh': '처음부터 다시 받기',
        'existing_fresh_desc': '기존에 받아둔 것을 무시하고 사이트 전체를 새로 받아요.',
        'label_language': '언어',
        'caption_language': '언어를 바꾸면 앱을 다시 시작해야 적용됩니다.',

        'confirm_title': '미러링을 시작할까요?',
        'confirm_header': '이 설정으로 시작할까요?',
        'summary_project_name': '프로젝트 이름',
        'summary_save_location': '저장 위치',
        'summary_target_urls': '대상 주소',
        'summary_action': '수집 방식',
        'summary_scope': '수집 범위',
        'summary_power': '완료 후 동작',
        'scope_unlimited': '제한 없음 (사이트 전체)',
        'scope_n_levels': '{depth} 단계까지',
        'power_text_after_hours': '{hours}시간 뒤 컴퓨터 종료',
        'power_text_on_complete': '완료되면 컴퓨터 종료',
        'power_text_none': '안 함',
        'url_count': '{n}개',

        'warn_need_url': '[경고] 받을 주소를 최소 하나 이상 입력해주세요!',
        'warn_need_project_name': '[경고] 프로젝트 이름을 입력해주세요!',
        'error_engine_missing': '[ERROR] 다운로드 엔진 경로 누락: {path}',
        'log_engine_init': 'MirrorX0 다운로드 엔진을 준비하는 중...',
        'warn_disk_critical': (
            '[경고] 디스크 여유 공간이 부족해({free}MB 남음) 시작하지 않습니다. '
            '공간을 확보한 뒤 다시 시도해주세요.'
        ),
        'warn_disk_low': '[경고] 디스크 여유 공간이 얼마 남지 않았습니다({free}MB 남음). 계속 진행합니다.',
        'log_project_folder': '프로젝트 폴더: {path}',
        'log_command': '명령어 실행: {cmd}',
        'log_user_stopped': '사용자에 의해 수집이 강제 중지되었습니다.',
        'log_success': '미러링이 성공적으로 완료되었습니다.',
        'log_done_with_errors': ('완료했어요. {n}개 링크는 받지 못했는데, 대개 사이트에 원래부터 깨져 있는 '
                                 '링크(404)예요. 받아온 파일 자체는 정상입니다.'),
        'log_done_code': '미러링 종료 (종료 코드: {code})',
        'log_fatal_error': '치명적 오류 발생: {result}',
        'warn_folder_not_found': '[경고] 폴더를 찾을 수 없습니다.',
        'log_prefs_saved': '환경설정이 저장되었습니다.',
        'warn_shutdown_schedule_failed': '[경고] 종료 예약에 실패했습니다: {e}',
        'notice_shutdown_scheduled': '[알림] {reason} — {mins}분 뒤 컴퓨터가 종료되도록 예약했습니다.',
        'notice_shutdown_cancelled': '[알림] 예약된 컴퓨터 종료를 취소했습니다.',
        'shutdown_banner_text': '{reason} — 약 {mins}분 뒤 컴퓨터가 종료됩니다',
        'reason_after_hours': '지정한 시간이 지나 예약된 종료',
        'reason_on_complete': '미러링이 끝나 예약된 종료',

        'panel_safety': '안전장치',
        'safety_pause_enable': '요청 사이 텀 두기',
        'safety_pause_caption': (
            '요청마다 무작위로 시간을 두고 받습니다. 느려지지만 대상 사이트에 부담을 덜 주고 '
            '차단당할 확률을 낮춰줍니다.'
        ),
        'safety_pause_between': '텀',
        'safety_pause_and': '~',
        'safety_pause_unit': '초',
        'label_smart_pause_enable': '페이지 사이 텀 두기',
        'caption_smart_pause': (
            '페이지를 열기 전에 무작위로 잠깐 쉽니다. 느려지지만, 사이트가 차단할 확률을 낮춰줘요 — '
            '큰 사이트를 받을 땐 켜두는 게 좋아요.'
        ),
        'safety_maxtime_enable': '최대 실행 시간 제한',
        'safety_maxtime_label': '시간 후 중단',
        'safety_maxtime_caption': '완료 여부와 상관없이 지정한 시간이 지나면 자동으로 멈춥니다.',
        'safety_maxsize_enable': '전체 용량 제한',
        'safety_maxsize_label': 'MB 넘으면 중단',
        'safety_maxsize_caption': '지정한 용량만큼 받으면 자동으로 멈춥니다.',
        'safety_hostcontrol_label': '느린 호스트 자동 포기',
        'hostcontrol_none': '포기 안 함',
        'hostcontrol_timeout': '타임아웃 시',
        'hostcontrol_slow': '느릴 때',
        'hostcontrol_both': '타임아웃 또는 느릴 때',
        'safety_hostcontrol_caption': '특정 호스트가 계속 타임아웃되거나 너무 느리면 일찍 포기하고 넘어갑니다.',
        'btn_load_url_file': '파일에서 불러오기',
        'dialog_load_url_file_title': '한 줄에 하나씩 URL이 담긴 텍스트 파일 선택',
        'log_loaded_urls': '파일에서 URL {n}개를 불러왔습니다.',
        'warn_url_file_failed': '[경고] 파일을 읽을 수 없습니다: {e}',

        'section_advanced': '고급',
        'label_referer': 'Referer 헤더',
        'caption_referer': '선택사항입니다. 모든 요청에 Referer 헤더로 전송됩니다.',
        'label_lang_header': '선호 언어 헤더',
        'caption_lang_header': (
            '사이트에 Accept-Language 헤더로 전송됩니다 (예: "ko, en"). 이 앱 자체의 화면 언어와는 '
            '별개입니다.'
        ),
        'label_custom_headers': '커스텀 HTTP 헤더',
        'caption_custom_headers': '한 줄에 하나씩, "헤더이름: 값" 형식으로 입력하세요. 필요 없으면 비워두세요.',
        'label_cookies_file': '쿠키 파일',
        'caption_cookies_file': '선택사항입니다. 로그인이 필요한 사이트에 쓰는 Netscape 형식 cookies.txt.',
        'dialog_cookies_file_title': 'cookies.txt 파일 선택',
        'label_link_format': '저장된 페이지의 링크 형식',
        'link_format_relative': '상대 경로 (기본)',
        'link_format_absolute': '절대 경로',
        'link_format_original': '원본 그대로 유지',
        'caption_link_format': '그대로 두세요. 기본값이면 폴더를 옮겨도 링크가 그대로 살아 있어요.',
        'label_near_files': '사이트 바로 바깥의 관련 파일도 함께 받기',
        'caption_near_files': '받는 범위 바로 바깥에 있는 이미지가 빠졌을 때 켜보세요.',
        'label_conn_per_sec': '초당 새 연결 수',
        'caption_conn_per_sec': '사이트가 차단할 때 부담을 줄이는 또 다른 방법이에요. 0이면 기본값 사용.',
        'label_warc': 'WARC 아카이브도 함께 저장',
        'caption_warc': '일반 미러링 결과와 함께 아카이빙 도구용 표준 .warc 파일도 만듭니다.',
        'label_search_index': '검색 인덱스 만들기',
        'caption_search_index': '받아둔 페이지를 단어로 검색하고 싶을 때만 켜세요. 기본은 꺼짐.',

        'tab_schedule': '스마트 크롤링',
        'nav_home': '홈',
        'nav_preferences': '환경설정',
        'dashboard_greeting': 'MirrorX0로 지금까지 한 일을 한눈에 볼 수 있어요.',
        'section_overview': '한눈에 보기',
        'metric_total_projects': '전체 프로젝트',
        'metric_total_size': '받은 총 용량',
        'metric_success_rate': '성공률',
        'metric_activity': '최근 활동',
        'metric_scheduled': '예약된 작업',
        'caption_success_rate': '성공 {success} · 오류 {errors}',
        'panel_recent_previews': '최근 받은 사이트',
        'label_no_previews': '아직 받은 게 없어요 — 미러링을 시작하면 여기에 보여요.',
        'panel_schedule_list': '스마트 스케줄러',
        'caption_schedule_list': (
            'MirrorX0을 꺼두어도 지정한 시각에 자동으로 실행돼요 — 컴퓨터가 켜져 있고 '
            '로그인된 상태여야 합니다 (잠금 화면은 괜찮아요).'
        ),
        'label_no_jobs': '아직 스마트 크롤링을 설정하지 않았어요.',
        'btn_new_job': '새 스마트 크롤링',
        'summary_schedule_value': '{n}개 등록됨',
        'summary_schedule_none': '등록된 예약 없음',
        'btn_edit_job': '수정',
        'btn_delete_job': '삭제',
        'job_mode_httrack': '빠르게 (일반 사이트)',
        'job_mode_smart': '스마트 (브라우저 렌더링)',
        'job_mode_both': '둘 다',
        'schedule_type_once': '1회',
        'schedule_type_hourly': '매시간',
        'schedule_type_daily': '매일',
        'schedule_type_weekly': '매주',
        'job_status_never_run': '실행 전',
        'job_status_running': '실행 중',
        'job_status_success': '완료',
        'job_status_errors': '오류와 함께 완료',
        'job_status_error': '실패',
        'dialog_job_title': '예약 작업',
        'label_job_name': '작업 이름',
        'label_job_mode': '크롤링 방식',
        'label_schedule_type': '반복',
        'label_schedule_time': '시각',
        'label_schedule_interval': '몇 시간마다 — "매시간"일 때 사용',
        'label_schedule_date': '날짜 (YYYY-MM-DD) — "1회"일 때 사용',
        'label_schedule_weekdays': '요일 — "매주"일 때 사용',
        'weekday_mon': '월', 'weekday_tue': '화', 'weekday_wed': '수', 'weekday_thu': '목',
        'weekday_fri': '금', 'weekday_sat': '토', 'weekday_sun': '일',
        'caption_schedule_note': '컴퓨터가 켜져 있고 로그인된 상태여야 실행돼요 — 잠금 화면은 괜찮아요.',
        'warn_job_need_name': '[경고] 작업 이름을 입력해주세요!',
        'warn_job_need_url': '[경고] 주소를 최소 하나 이상 입력해주세요!',
        'warn_job_need_date': '[경고] 1회 실행은 날짜를 입력해주세요!',
        'warn_job_invalid_date': '[경고] 날짜는 YYYY-MM-DD 형식으로 입력해주세요!',
        'log_job_saved': '예약 작업이 저장되었습니다.',
        'log_job_deleted': '예약 작업이 삭제되었습니다.',
        'warn_job_schedule_failed': '[경고] 예약 작업 등록에 실패했습니다: {e}',

        'section_ai': 'AI 크롤링',
        'label_ai_provider': 'AI 프로바이더',
        'caption_ai_provider': (
            '필드 제안과 데이터 추출에 어떤 AI를 사용할지 선택합니다. 기본값은 Ollama — '
            'API 키 없이 무료로, 내 컴퓨터에서 직접 실행되지만 더 느립니다. 아래에 클라우드 '
            'API 키를 입력하면 더 빠른 유료 프로바이더로 바뀝니다.'
        ),
        'caption_ollama_tradeoff': (
            'Ollama (무료, 기본값): API 키 필요 없이 내 컴퓨터에서 전부 실행되어 사용료가 없지만, '
            '더 느리고 Ollama 앱 설치(ollama.com)와 모델 다운로드(예: "ollama pull llama3.2")가 '
            '필요합니다. Anthropic/OpenAI/Gemini (유료): 별도 설치 없이 훨씬 빠르지만, 본인 API '
            '키가 필요하고 사용할 때마다 비용이 듭니다.'
        ),
        'ollama_status_checking': 'Ollama 상태를 확인하는 중…',
        'ollama_status_not_installed': 'Ollama가 아직 설치되지 않았어요. 무료로 쓰려면 설치가 필요해요.',
        'ollama_status_not_running': 'Ollama가 설치는 됐는데 실행 중이 아니에요.',
        'ollama_status_no_model': 'Ollama는 실행 중인데, 받아둔 모델이 없어요.',
        'ollama_status_ready': 'Ollama 사용 준비 완료 ({model}).',
        'ollama_status_working': '진행 중… 몇 분 걸릴 수 있어요.',
        'btn_ollama_install': 'Ollama 설치하기',
        'btn_ollama_start': 'Ollama 실행하기',
        'btn_ollama_pull': '모델 받기',
        'btn_ollama_check': '다시 확인',
        'label_api_key_anthropic': 'Anthropic API 키',
        'label_api_key_openai': 'OpenAI API 키',
        'label_api_key_gemini': 'Google Gemini API 키',
        'caption_api_key': 'AI 기반 데이터 추출에 사용됩니다. 이 컴퓨터에만 저장되고 위에서 고른 프로바이더에만 전송됩니다.',
        'label_ai_extract_enable': 'AI로 데이터 추출하기',
        'label_ai_instruction': '어떤 정보를 추출할까요?',
        'caption_ai_instruction': '무엇을 뽑을지 한 문장으로 적어주세요.',
        'placeholder_ai_instruction': '예: 상품명, 가격, 리뷰 개수',
        'btn_propose_fields': '필드 확인',
        'label_extract_fields': '추출할 필드',
        'field_col_name': '필드 이름',
        'field_col_label': '설명',
        'field_col_type': '타입',
        'btn_add_field': '+ 필드 추가',
        'label_export_formats': '내보내기 형식',
        'btn_run_extraction': '추출 실행',
        'dialog_ai_extract_title': 'AI 데이터 추출',
        'label_target_folder': '대상 폴더',
        'caption_target_folder': '먼저 "사이트 다운로드"로 받아둔 폴더를 골라주세요.',
        'label_save_location': '저장 위치',
        'caption_save_location': '뽑아낸 표가 저장될 위치입니다.',
        'warn_choose_folder': '[경고] 먼저 폴더를 선택해주세요.',
        'dialog_clean_organize_title': '정리된 사본 만들기',
        'caption_clean_organize_intro': (
            '받아둔 사이트를 css/js/images/fonts 폴더로 정돈한 사본을 새로 만듭니다. '
            '원본 폴더는 그대로 둡니다.'
        ),
        'btn_run_clean_organize': '정리 시작',
        'caption_extract_estimate': (
            '예상: {files}개 페이지에 대해 API 호출 약 {calls}회 '
            '(총 약 {rows}행). 패턴 감지로 AI를 부르지 않고 무료로 미리 계산한 값입니다.'
        ),
        'btn_ai_extract': 'AI 추출',
        'warn_need_api_key': '[경고] 환경설정에서 Anthropic API 키를 먼저 등록해주세요!',
        'warn_need_instruction': '[경고] 어떤 정보를 추출할지 입력해주세요!',
        'warn_need_sample_page': '[경고] 필드를 제안할 샘플 페이지를 가져오지 못했습니다.',
        'warn_propose_failed': '[경고] 필드 제안에 실패했습니다: {e}',
        'log_fields_proposed': '필드 {n}개를 제안받았습니다.',
        'warn_need_fields': '[경고] 추출할 필드를 최소 하나 이상 추가해주세요!',
        'log_ai_extract_started': 'AI 추출을 시작합니다...',
        'warn_ai_skip_no_key': '[AI 추출] API 키가 설정되어 있지 않아 건너뜁니다.',

        'btn_pagination_extract': '목록 페이지네이션 추출',
        'dialog_pagination_title': '여러 페이지로 나뉜 목록 추출',
        'caption_pagination_intro': (
            '"다음", "더보기" 등으로 계속 다음 페이지가 이어지는 목록/카탈로그 페이지용입니다. '
            '사이트 전체를 먼저 받을 필요 없이, 시작 페이지 주소와 뽑고 싶은 항목만 알려주면 '
            '다음 페이지를 계속 따라가며 하나의 표로 이어붙여줍니다.'
        ),
        'label_pagination_start_url': '시작 페이지 주소',
        'label_pagination_max_pages': '최대 몇 페이지까지 따라갈지',
        'warn_pagination_need_url': '[경고] 시작 페이지 주소를 입력해주세요!',
        'log_pagination_started': '페이지네이션 추출을 시작합니다...',
        'log_pagination_no_rows': '[페이지네이션 추출] 추출된 행이 없습니다.',

        'btn_click_select': '클릭해서 고르기',
        'dialog_click_select_title': '클릭해서 고르기',
        'caption_click_select_intro': (
            '자동 감지가 헷갈려하는 페이지에서(또는 그냥 정확하게 고르고 싶을 때) 사용합니다. '
            '실제 브라우저 창이 열리면, 항목 위에 마우스를 올려 강조 표시를 확인하고 '
            '예시가 될 항목 하나를 클릭하세요. 그것과 구조적으로 같은 항목을 전부 찾아 표로 만들어줍니다.'
        ),
        'label_click_select_url': '페이지 주소',
        'btn_open_browser_pick': '브라우저 열고 고르기',
        'status_click_select_waiting': '브라우저 창이 열렸습니다 — 항목 위에 마우스를 올려보고 예시 하나를 클릭하세요...',
        'status_click_select_picked': '비슷한 항목 {n}개를 찾았습니다 (셀렉터: {selector}).',
        'warn_click_select_failed': '[경고] 항목을 고르지 못했습니다: {e}',
        'log_click_select_started': '클릭해서 고르기 추출을 시작합니다...',
        'log_click_select_no_rows': '[클릭해서 고르기] 추출된 행이 없습니다.',

        'btn_data_tools': '데이터 도구',
        'dialog_data_tools_title': '데이터 도구',
        'caption_data_tools_intro': (
            '받아온 페이지를 깔끔한 표 데이터로 바꿉니다. 지금 상황에 맞는 도구를 골라주세요.'
        ),
        'desc_ai_extract': (
            '이미 사이트를 받아뒀나요? 원하는 필드(이름, 가격 등)만 골라 모든 페이지에서 '
            '표로 뽑아냅니다.'
        ),
        'desc_pagination_extract': '"다음"으로 이어지는 목록을 끝까지 따라가 하나의 표로 만듭니다.',
        'desc_click_select': '브라우저에서 예시 하나를 클릭하면 비슷한 항목을 전부 찾아줍니다.',
        'desc_clean_organize': '받아둔 사이트를 css/js/images/fonts로 정돈한 사본을 만듭니다.',
        'caption_tool_needs_project': '완료된 프로젝트가 필요합니다(먼저 사이트를 미러링/스마트 크롤링하세요).',
        'btn_use_tool': '사용',

        'btn_clean_organize': '정리된 사본 만들기',
        'log_clean_organize_started': (
            '정리된 사본을 만드는 중입니다 (css/js/images/fonts로 재배치, 엔진 관리 '
            '파일 제거). 원본 폴더는 그대로 둡니다...'
        ),
        'log_clean_organize_done': '정리된 사본을 만들었습니다: {path}',
        'warn_clean_organize_failed': '[경고] 정리된 사본을 만들지 못했습니다: {e}',

        'log_ai_extract_offer_refine': '{n}개 행을 뽑았어요. 이 표를 자연어로 다듬어볼까요?',
        'dialog_refine_title': '표 다듬기',
        'caption_refine_intro': '{n}개 행이 있어요. 수식 몰라도 돼요 - 원하는 걸 그냥 말로 설명해주세요.',
        'caption_refine_saved_at': '저장 위치: {path}',
        'label_refine_instruction': '무엇을 바꾸고 싶으신가요?',
        'caption_refine_examples': (
            '예: "B열은 빼고 C열을 B열에 넣어줘" · "가격 결측치는 최빈값으로 채워줘" · '
            '"중복된 행은 지워줘"'
        ),
        'btn_propose_refine': '방법 제안받기',
        'btn_apply_refine': '적용',
        'btn_skip': '건너뛰기',
        'warn_refine_need_instruction': '[경고] 먼저 무엇을 바꿀지 설명해주세요.',
        'warn_refine_failed': '[경고] 제안을 받지 못했습니다: {e}',
        'preview_refine_summary': '행: {rows_before}개 -> {rows_after}개',
        'preview_columns_added': '추가된 열: {cols}',
        'preview_columns_removed': '없어진 열: {cols}',
        'preview_refine_warnings': '건너뜀: {warnings}',
        'preview_refine_none': '요청에 맞는 변경을 찾지 못했어요. 다르게 설명해보세요.',
        'log_refine_applied': '다듬은 표를 저장했어요 ({n}개 파일).',

        'btn_ai_scope_rules': 'AI로 규칙 제안받기',
        'dialog_ai_scope_title': 'AI 다운로드 범위 규칙',
        'label_scope_goal': '무엇을 받고 싶으신가요?',
        'caption_scope_goal': '한 문장으로 설명해주세요. 예: "레시피 카테고리만 받고 로그인/장바구니 페이지는 빼줘".',
        'btn_get_scope_rules': '규칙 제안받기',
        'caption_scope_cost': (
            '시작 주소에서 링크 샘플을 조금 살펴본 뒤, 단 한 번의 AI 호출로 규칙을 제안합니다 — '
            '사이트 크기와 무관하게 비용이 고정됩니다.'
        ),
        'label_proposed_rules': '제안된 규칙 (적용 전에 수정할 수 있어요)',
        'btn_apply_rules': '적용',
        'warn_scope_need_goal': '[경고] 무엇을 받고 싶은지 입력해주세요!',
        'warn_scope_need_url': '[경고] 먼저 주소를 입력해주세요!',
        'log_fetching_link_sample': '링크 샘플을 가져오는 중...',
        'warn_scope_no_links': '[경고] 분석할 링크를 찾지 못했습니다.',
        'warn_scope_failed': '[경고] 규칙 제안을 받지 못했습니다: {e}',
        'log_scope_rules_applied': 'AI가 제안한 규칙을 적용했습니다.',

        'panel_recent_projects': '최근 프로젝트',
        'caption_recent_projects': '이전에 받던 프로젝트를 이어서 하거나, 그때 설정을 다시 불러올 수 있어요.',
        'label_no_projects': '아직 받은 프로젝트가 없어요.',
        'btn_load_project': '불러오기',
        'btn_continue_project': '이어받기',
        'btn_delete_project': '삭제',
        'proj_status_never': '실행 전',
        'proj_status_running': '실행 중',
        'proj_status_success': '완료',
        'proj_status_errors': '오류와 함께 완료',
        'proj_status_failed': '실패',
        'proj_url_count': '{n}개',
    },
}

_current_lang = 'en'


def set_language(lang):
    global _current_lang
    _current_lang = lang if lang in STRINGS else 'en'


def t(key, **kwargs):
    template = STRINGS.get(_current_lang, STRINGS['en']).get(key, STRINGS['en'].get(key, key))
    return template.format(**kwargs) if kwargs else template


def get_actions():
    return [(code, t(f'action_{code}')) for code in ('1', '2', '3', '4', '5')]


def get_robots_options():
    return [(code, t(f'robots_{code}')) for code in ('0', '1', '2')]


def get_filter_groups():
    """파일 종류 체크박스 그룹: (표시 이름, 매칭 확장자들, 기본 선택 여부)"""
    return [
        (t('filter_images'), ['png', 'gif', 'jpg', 'jpeg', 'webp', 'svg', 'ico', 'avif', 'bmp', 'tiff'], True),
        (t('filter_style_script'), ['css', 'js', 'mjs'], True),
        (t('filter_docs'),
         ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'hwp', 'hwpx', 'txt', 'csv', 'epub'], False),
        (t('filter_media'), ['mp4', 'mp3', 'avi', 'webm', 'wav', 'mkv', 'mov', 'flac', 'ogg', 'm4a'], False),
        (t('filter_archive'), ['zip', 'rar', '7z', 'tar', 'gz'], False),
    ]


def get_job_labels():
    return {
        'waiting (throttle)': t('job_waiting'),
        'receiving files': t('job_receiving'),
    }

