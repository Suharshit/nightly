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

import os

# On Spaces, Gradio turns on server-side rendering, which starts a Node server during the mounted
# page's startup. It took the first free port, 7860, before uvicorn could bind it
# ("address already in use"). The placeholder page does not need SSR.
os.environ["GRADIO_SSR_MODE"] = "false"

import gradio as gr  # noqa: E402  (after the SSR switch)
import uvicorn  # noqa: E402

from api.app.main import app  # noqa: E402


def _gpu_stub() -> str:
    return "ok"


if spaces is not None:
    _gpu_stub = spaces.GPU(_gpu_stub)

with gr.Blocks(title="nightly API") as ui:
    gr.Markdown("The API behind [nightly](https://nightlyjobs.vercel.app). "
                "Health check: [/health](/health).")
    _out = gr.Textbox(visible=False)
    gr.Button(visible=False).click(_gpu_stub, outputs=_out)

app = gr.mount_gradio_app(app, ui, path="/")

# Listen where Gradio's own launch() would: the Space sets GRADIO_SERVER_PORT / _NAME and
# forwards its public port there (7860 itself is taken on ZeroGPU before app.py starts).
HOST = os.getenv("GRADIO_SERVER_NAME", "0.0.0.0")
PORT = int(os.getenv("GRADIO_SERVER_PORT", "7860"))

if __name__ == "__main__":
    print(f"nightly API listening on {HOST}:{PORT}", flush=True)
    uvicorn.run(app, host=HOST, port=PORT)
