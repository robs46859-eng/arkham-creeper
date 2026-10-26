# Embedded report typography

The measured report embeds three unmodified Latin WOFF2 assets from the official Google Fonts distribution in `creeper/report_fonts.py`. `REPORT_FONT_CSS` contains data URLs, so rendering makes no external font requests and requires no CDN scripts. The shared SIL Open Font License 1.1 text and all three copyright notices are embedded in that CSS for redistributions of the standalone report. The original per-family notices are retained alongside this document.

The terminal report uses Cinzel headings, JetBrains Mono body/data text, and Space Mono metadata.

| Family | Style | Subset | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| Cinzel | normal 700 | Latin | 15,184 | `8efa224fe70fef188a39c095e218b81fd31061809f2752537e33a9ec7b9c2263` |
| JetBrains Mono | normal 400 | Latin | 21,168 | `14425ba9c695763c1547f48a206b7aa60350a33ae23de09f0407877f3fcd89eb` |
| Space Mono | normal 400 | Latin | 16,520 | `fb4a81a2d0a893e5c38c394a7e716a1cef0b24610a0af49c96f6d529bd66bf2b` |

Total binary font size: 52,872 bytes before base64 encoding. Other glyphs fall back to the renderer's system-font stack. No font was edited or renamed locally.

## Official sources

Retrieved October 25, 2026 using the [Google Fonts CSS API](https://fonts.googleapis.com/css2?family=Cinzel:wght@700&family=JetBrains+Mono:wght@400&family=Space+Mono:wght@400&display=swap).

- [Cinzel Latin WOFF2](https://fonts.gstatic.com/s/cinzel/v26/8vIU7ww63mVu7gtR-kwKxNvkNOjw-jHgfY3lDQ.woff2), [original license](https://github.com/google/fonts/blob/main/ofl/cinzel/OFL.txt), [upstream project](https://github.com/NDISCOVER/Cinzel).
- [JetBrains Mono Latin WOFF2](https://fonts.gstatic.com/s/jetbrainsmono/v24/tDbY2o-flEEny0FZhsfKu5WU4zr3E_BX0PnT8RD8yKxTOlOV.woff2), [original license](https://github.com/google/fonts/blob/main/ofl/jetbrainsmono/OFL.txt), [upstream project](https://github.com/JetBrains/JetBrainsMono).
- [Space Mono Latin WOFF2](https://fonts.gstatic.com/s/spacemono/v17/i7dPIFZifjKcF5UAWdDRYEF8RQ.woff2), [original license](https://github.com/google/fonts/blob/main/ofl/spacemono/OFL.txt), [upstream project](https://github.com/googlefonts/spacemono).

These fonts retain the SIL Open Font License 1.1; the application's code license does not replace their license. Font authors do not endorse this project.
