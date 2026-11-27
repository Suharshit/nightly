"""Entry point for the Hugging Face Space.

Free accounts can only create Gradio Spaces on ZeroGPU hardware. The Space runs `python app.py`.
Gradio's server is FastAPI, so the nightly API is served as it is, with a small Gradio page
mounted at / (the API's own routes are registered first, so they win). The models run on CPU;
no GPU is ever requested.

ZeroGPU only starts an app that has a @spaces.GPU function wired to a Gradio event, so one
stub sits behind a hidden button. Nothing calls it, so no GPU quota is used.
"""

try:  # Only installed on ZeroGPU. It must be imported before torch and gradio.
    import spaces
except ImportError:
    spaces = None

import gradio as gr
import uvicorn

from api.app.main import app


def _gpu_stub() -> str:
    return "ok"


if spaces is not None:
    _gpu_stub = spaces.GPU(_gpu_stub)

with gr.Blocks(title="nightly API") as ui:
    gr.Markdown("The API behind [nightly](https://nightlyjobs.vercel.app). "
                "Health check: [/health](/health). API docs: [/docs](/docs).")
    _out = gr.Textbox(visible=False)
    gr.Button(visible=False).click(_gpu_stub, outputs=_out)

app = gr.mount_gradio_app(app, ui, path="/")

PORT = 7860


def _port_holder(port: int) -> str:
    """Who listens on `port`, from /proc (Linux only). For the Space log when the port is taken."""
    import glob
    import os
    inodes = set()
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            for row in open(table).read().splitlines()[1:]:
                cols = row.split()
                if int(cols[1].rsplit(":", 1)[1], 16) == port and cols[3] == "0A":  # LISTEN
                    inodes.add(cols[9])
        except OSError:
            pass
    holders = []
    for fd in glob.glob("/proc/[0-9]*/fd/*"):
        try:
            target = os.readlink(fd)
        except OSError:
            continue
        if target.startswith("socket:[") and target[8:-1] in inodes:
            pid = fd.split("/")[2]
            try:
                cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode()
            except OSError:
                cmd = "?"
            holders.append(f"pid {pid}: {cmd.strip()[:200]}")
    found = "; ".join(sorted(set(holders)))
    return found or f"listening inodes {sorted(inodes)}, owner not visible"


def _port_free(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


if __name__ == "__main__":
    if not _port_free(PORT):
        # Diagnose instead of loading the models first: only the end of the log is visible.
        import os
        import sys
        print(f"PORT {PORT} IS TAKEN by {_port_holder(PORT)}", flush=True)
        print(f"me: pid {os.getpid()} argv {sys.argv}; parent: "
              f"{open(f'/proc/{os.getppid()}/cmdline', 'rb').read().replace(b'\0', b' ')[:200]!r}",
              flush=True)
        print("env:", {k: v for k, v in os.environ.items()
                       if k.startswith("GRADIO_") or k in ("PORT", "SPACES_ZERO_GPU")}, flush=True)
        sys.exit(1)
    uvicorn.run(app, host="0.0.0.0", port=PORT)
