from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from starlette.templating import Jinja2Templates
import uvicorn, aiohttp, asyncio
from io import BytesIO, StringIO
from fastai import *
from fastai.vision import *
import base64
import pdb
from utils import *

export_file_url = 'https://www.dropbox.com/s/xlwwdf5zmz3ehvs/export.pkl?dl=0'
export_file_name = 'export.pkl'
classes = ['a', 'b', 'c']

path = Path(__file__).parent

templates = Jinja2Templates(directory='app/templates')
app = Starlette()
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_headers=['X-Requested-With', 'Content-Type'])
app.mount('/static', StaticFiles(directory='app/static'))

async def download_file(url, dest):
    if dest.exists(): return
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.read()
            with open(dest, 'wb') as f: f.write(data)


async def setup_learner():
    await download_file(export_file_url, path/'models'/export_file_name)
    defaults.device = torch.device('cpu')
    learn = load_learner(path/'models', export_file_name)
    return learn

loop = asyncio.get_event_loop()
tasks = [asyncio.ensure_future(setup_learner())]
learn = loop.run_until_complete(asyncio.gather(*tasks))[0]
loop.close()

@app.route("/upload", methods=["POST"])
async def upload(request):
    data = await request.form()
    img_bytes = await (data["file"].read())

    img = open_image(BytesIO(img_bytes))
    x, y, z = img.data.shape

    max_size = 1000
    y_new, z_new = get_resize(y, z, max_size)

    data_bunch = (ImageImageList.from_folder(path).split_none().label_from_func(lambda x: x)
          .transform(get_transforms(do_flip=False), size=(y_new,z_new), tfm_y=True)
          .databunch(bs=2, no_check=True).normalize(imagenet_stats, do_y=True))

    data_bunch.c = 3
    learn.data = data_bunch
    _,img_hr,losses = learn.predict(img)

    im = Image(img_hr.clamp(0,1))

    im_data = image2np(im.data*255).astype(np.uint8)

    img_io = BytesIO()

    PIL.Image.fromarray(im_data).save(img_io, 'PNG')

    img_io.seek(0)

    img_str = base64.b64encode(img_io.getvalue()).decode()
    img_str = "data:image/png;base64," + img_str

    return templates.TemplateResponse('output.html', {'request' : request, 'b64val' : img_str})


@app.route("/")
def form(request):
    index_html = path/'static'/'index.html'
    return HTMLResponse(index_html.open().read())

if __name__ == "__main__":
    if "serve" in sys.argv: uvicorn.run(app = app, host="0.0.0.0", port=5000)
