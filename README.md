# AIM Planet (bkmade.nyc) v0.2

## Where things live
- `content/diary.txt`  the journal. Plain text. This is the file you will edit most.
- `content/videos.txt` the video menu. One line per video.
- `img/`               pictures for diary entries
- `v/`                 video files
- `index.html`         the site itself (layout, colors, robot replies)

## Add a diary entry (no graphics needed)
1. On GitHub, open `content/diary.txt` and click the pencil.
2. Paste this at the top, under the notes, and change the words:

```
---
title: my new entry
date: 12 Nov 2026 | 9:00 pm
mood: sleepy
tags: ramble

Write whatever here. A blank line starts a new paragraph.
```

3. Commit. The site updates in about a minute.

With no `image:` line the page builds a title card for the entry by itself.
To use a picture, upload it to `img/` and add `image: img/yourfile.png`.
Every optional line (sticker, note, stamp, receipt, scratch, video) is explained at the top of `diary.txt`.

## Add a video
Upload the .mp4 to `v/`, then add a line to `content/videos.txt`:  `My Title | v/myfile.mp4`

## Other edits (in index.html)
- Intro text and bio: search for `class="hello"`.
- Robot replies: the `RULES` list in the script. Set `CONTACT` to hand out an email or link.
- Colors and fonts: the `:root` block at the top of the stylesheet.
- The floating star is decoration only right now. It is the `#star` element, ready for your game.

## Put it on GitHub Pages
1. Create a repo and push these files to the `main` branch (keep `CNAME` and `.nojekyll`).
2. Repo Settings > Pages > Source: "Deploy from a branch", branch `main`, folder `/ (root)`.
3. Custom domain: `bkmade.nyc`. Tick "Enforce HTTPS" once the certificate is ready.
4. GoDaddy DNS for bkmade.nyc:
   - A records for `@`: 185.199.108.153, 185.199.109.153, 185.199.110.153, 185.199.111.153
   - CNAME for `www`: `<your-github-username>.github.io`

Pages from a private repo needs a paid GitHub plan (Pro or above). The repo stays private, the site itself is public.

## Preview on your computer
The diary loads from a text file, so double-clicking index.html will not show entries. Run `python3 -m http.server` in this folder and open http://localhost:8000.

`loops.py` is the Blender script that rendered the four videos.
