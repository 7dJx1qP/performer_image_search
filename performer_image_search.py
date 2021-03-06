import cloudscraper
import io
import json
import subprocess
import sys
import PySimpleGUI as sg
from PIL import Image, ImageTk
from stashlib.common import get_timestamp
from stashlib.stash_database import StashDatabase
from stashlib.stash_models import *
import stashlib.log as log
from config import *

def get_img_data(f, maxsize=(1200, 850), first=False, bytes=None):
    """Generate image data using PIL
    """
    if not bytes:
        img = Image.open(f)
    else:
        img = Image.open(io.BytesIO(bytes))
    img.thumbnail(maxsize)
    if first:                     # tkinter is inactive the first time
        bio = io.BytesIO()
        img.save(bio, format="PNG")
        del img
        return bio.getvalue()
    return ImageTk.PhotoImage(img)

def scrape_image(url):
    log.LogTrace(f"scrape_image {url}")
    scraper = cloudscraper.create_scraper()
    try:
        scraped = scraper.get(url, timeout=(3,7))
    except Exception as e:
        log.LogError("scrape error %s" %e )
        return None
    if scraped.status_code >= 400:
        log.LogError("HTTP error %s" % scraped.status_code)
        return None
    return scraped.content

def do_search(name):
    subprocess.run([BROWSER_PATH, BROWSER_PRIVATE_FLAG, 'https://www.google.com/search?q={}+porn&tbm=isch'.format(name.removesuffix(' *').replace(' ', '+'))])

def search(db: StashDatabase):
    """Loop through actress image folders in <outdir> and display images in folder
    Clicking an image sets the performer to use the image
    """

    log.LogTrace("search start")

    tagged_performer_ids = []
    if TAG_NAME:
        log.LogTrace(f"selecting tag named {TAG_NAME}")
        tag = db.tags.selectone_name(TAG_NAME)
        if not tag:
            log.LogTrace(f"tag not found. creating tag")
            db.tags.insert(TAG_NAME, get_timestamp(), get_timestamp())
        tag = db.tags.selectone_name(TAG_NAME)
        if not tag:
            raise Exception(f"Could not create tag {TAG_NAME}")
        elif SHOW_UNTAGGED_ONLY:
            log.LogTrace(f"SHOW_UNTAGGED_ONLY=True")
            tagged_performer_ids = [performer_tag.performer_id for performer_tag in db.performers_tags.select_tag_id(tag.id)]

    log.LogTrace(f"FAVORITES_ONLY={FAVORITES_ONLY}")
    if FAVORITES_ONLY:
        performers = [performer for performer in db.performers.select_favorite(1) if performer.id not in tagged_performer_ids]
    else:
        rows = db.fetchall("""SELECT * FROM performers""")
        performers = [PerformersRow().from_sqliterow(row) for row in rows]
        performers = [performer for performer in performers if performer.id not in tagged_performer_ids]

    log.LogTrace(f"SHOW_MISSING_IMAGE_ONLY={SHOW_MISSING_IMAGE_ONLY}")
    if SHOW_MISSING_IMAGE_ONLY:
        performer_ids_with_image = [PerformersImageRow().from_sqliterow(row).performer_id for row in db.performers_image.select()]
        performers = [performer for performer in performers if performer.id not in performer_ids_with_image]

    performers.sort(key=lambda x: x.name)

    log.LogTrace(f"IMAGE_WIDTH={IMAGE_WIDTH}, IMAGE_HEIGHT={IMAGE_HEIGHT}")
    IMGSIZE = (IMAGE_WIDTH, IMAGE_HEIGHT)

    sg.theme('SystemDefaultForReal')
    performer_counter_el = sg.Text("")
    performer_image_el = sg.Image()
    scrape_image_el = sg.Image()
    layout = [
        [
            performer_counter_el,
        ],
        [
            sg.Submit(button_text='Back', key='performer_back'), sg.Submit(button_text='Next', key='performer_next'),
            sg.Input(size=5, justification='right', default_text="1", key='performer_go_to_num'),
            sg.Submit(button_text='Go To', key='performer_go_to'),
            sg.Submit(button_text='Tag', key='tag')
        ],
        [
            performer_image_el
        ],
        [
            sg.Submit(button_text='Search', key='search'),
        ],
        [
            sg.Input(default_text="", key='download_url'),
            sg.Submit(button_text='Download', key='download_image'),
            sg.Submit(button_text='Set Image', key='set_image'),
        ],
        [
            scrape_image_el
        ],
    ]

    window = sg.Window('Performer Image Select', layout=layout, resizable=True,  return_keyboard_events=True, finalize=True)

    log.LogTrace(f"window created")

    def set_performer(performer_index):
        log.LogTrace(f"set_performer {performer_index}")
        performer_index = performer_index % len(performers)
        performer = performers[performer_index]

        window['performer_go_to_num'].update(performer_index + 1)
        performer_counter_el.update(f"{performer_index + 1} of {len(performers)} {performer.name}")

        performer_image = db.performers_image.selectone_performer_id(performer.id)
        if performer_image:
            performer_image_el.update(data=get_img_data(None, bytes=performer_image.image, maxsize=IMGSIZE, first=True))
        else:
            performer_image_el.update()

        window['download_url'].update('')
        scrape_image_el.update()

        return performer_index, performer, None

    performer_index, performer, scraped_performer_image = set_performer(0)

    def tag_performer():
        log.LogTrace(f"tag_performer")
        if tag and TAG_PERFORMERS:
            tag_ids = [performer_tag.tag_id for performer_tag in db.performers_tags.select_performer_id(performer.id)]
            if tag.id not in tag_ids:
                db.performers_tags.insert(performer.id, tag.id)
                log.LogInfo(f'Tagged {performer.name} {tag.name}')
            else:
                log.LogInfo(f'Performer {performer.name} already tagged {tag.name}')

    while True:
        event, values = window.read()
        if event:
            log.LogInfo(event)
        if event in (sg.WIN_CLOSED, 'Exit'):
            sys.exit(0)
        elif event == 'Cancel':
            sys.exit(0)
        elif event == 'performer_back' or event == 'Left:37' or event == 'a':
            performer_index, performer, scraped_performer_image = set_performer(performer_index - 1)
        elif event == 'performer_next' or event == 'Right:39' or event == 'd':
            performer_index, performer, scraped_performer_image = set_performer(performer_index + 1)
        elif event == 'performer_go_to':
            if values['performer_go_to_num'].isnumeric():
                performer_index, performer, scraped_performer_image = set_performer(int(values['performer_go_to_num']) - 1)
            else:
                window['performer_go_to_num'].update(performer_index + 1)
        elif event == 'search' or event == 's':
            do_search(performer.name)
            window['download_url'].update('')
        elif event == 'tag':
            tag_performer()
        elif event =='download_image' and values['download_url']:
            scraped_performer_image = scrape_image(values['download_url'])
            if scraped_performer_image:
                try:
                    scrape_image_el.update(data=get_img_data(None, bytes=scraped_performer_image, maxsize=IMGSIZE, first=True))
                except:
                    sg.popup('Image failed to load.')
                    scraped_performer_image = None
                    scrape_image_el.update()
            else:
                scrape_image_el.update()
        elif event == 'set_image':
            if scraped_performer_image:
                performer_image = db.performers_image.selectone_performer_id(performer.id)
                if performer_image:
                    db.execute("""UPDATE performers_image SET image = ? WHERE performer_id = ?""", (scraped_performer_image, performer.id))
                else:
                    db.performers_image.insert(performer.id, scraped_performer_image)
                log.LogInfo(f'Set {performer.name} image to {values["download_url"]}')
                tag_performer()
                performer_index, performer, scraped_performer_image = set_performer(performer_index + 1)
            else:
                sg.popup('No performer image downloaded. You must enter an image url and click download.')

def read_json_input():
    json_input = sys.stdin.read()
    return json.loads(json_input)
    
json_input = read_json_input()
mode_arg = json_input['args']['mode']

try:
    log.LogTrace(f"opening database {DATABASE_PATH}")
    db = StashDatabase(DATABASE_PATH)
except Exception as e:
    log.LogError(str(e))
    sys.exit(0)

try:
    log.LogInfo("mode: {}".format(mode_arg))

    if mode_arg == 'search':
        search(db)

except Exception as e:
    log.LogError(str(e))

db.close()

log.LogInfo('done')
output = {}
output["output"] = "ok"
out = json.dumps(output)
print(out + "\n")