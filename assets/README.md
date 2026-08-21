# Demo GIF

`demo.gif` is a screen capture of `http://localhost:3000` after `docker compose up --build`.

Beats:

1. Idle feed moving
2. Burst 50/2s, then cooldown
3. Stats + charts move
4. Click a flagged row → bipolar bars, hover/focus the **i** tooltip
5. Alerts footer: `Showing 1–50 of N` with Next enabled, click Next, click Previous

Encode from a 1280px-wide recording:

```bash
ffmpeg -i demo.mov -vf "fps=12,scale=1280:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" -loop 0 assets/demo.gif
gifsicle -O3 --lossy=80 assets/demo.gif -o assets/demo.gif
```

Cap: 8 MB. Not generated in CI.
