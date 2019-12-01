#!/usr/bin/python
# -*- coding: utf8 -*-

import os
import random
import re
import json

# install: pip install --upgrade arabic-reshaper
import arabic_reshaper

# install: pip install python-bidi
from bidi.algorithm import get_display

# install: pip install Pillow
from PIL import ImageFont
from PIL import Image
from PIL import ImageDraw

fontFile = "static/font/Samim.ttf"

# this was a 400x400 jpg file
# imageFile = "/Users/amirreza/pil/input.jpg"

try:
    from hashlib import md5
except ImportError:
    from md5 import md5

import tornado.httpserver
import tornado.ioloop
import tornado.web
from tornado.escape import xhtml_unescape
from tornado.options import define

from faunadb import query as q
from faunadb.client import FaunaClient

client = FaunaClient(secret="fnADZDRJZHACCPvDZ928toYh6dnhoqsB4daanp5n")


define("port", default=5000, help="run on the given port", type=int)

messages_file = os.path.join(os.path.dirname(__file__), 'disc_subjsctes.txt')
messages = {}

# Create a hash table of all discussion subjsctes
# with open(messages_file) as messages_input:
#     for line in messages_input.readlines():
#         messages[md5(line).hexdigest()] = line

num_re = re.compile(r"XNUM([0-9,]*)X")

def fill_line(message):
    nums = num_re.findall(message)

    while nums:
        start = 1
        end = 999
        value = nums.pop(0) or str(end)
        if "," in value:
            position = value.index(",")
            if position == 0: # XNUM,5X
                end = int(value[1:])
            elif position == len(value) - 1: # XNUM5,X
                start = int(value[:position])
            else: # XNUM1,5X
                start = int(value[:position])
                end = int(value[position+1:])
        else:
            end = int(value)
        if start > end:
            end = start * 2

        randint = random.randint(start, end)
        message = num_re.sub(str(randint), message, count=1)

    return message

def text_wrap(text, font, max_width):
    lines = []
    # If the width of the text is smaller than image width
    # we don't need to split it, just add it to the lines array
    # and return
    if font.getsize(text)[0] <= max_width:
        lines.append(text)
    else:
        # split the line by spaces to get words
        words = text.split(' ')
        i = 0
        # append every word to a line while its width is shorter than image width
        while i < len(words):
            line = ''
            while i < len(words) and font.getsize(line + words[i])[0] <= max_width:
                line = line + words[i] + " "
                i += 1
            if not line:
                line = words[i]
                i += 1
            # when the line gets longer than the max width do not append the word, 
            # add the line to the lines array
            lines.append(line)
    return lines

class MainHandler(tornado.web.RequestHandler):
    def get(self, message_hash=None):
        if not message_hash:
            page = q.paginate(q.match(q.index("confirmed"), 'True'))
            ns = q.map_(lambda a: q.select(["data"], q.get(a)), page)
            result = client.query(ns)['data']

            for message in result:
                messages[message['hash']] = message
            message_hash = random.choice(messages.keys())

            message = fill_line(messages[message_hash]['title'])
            suggester = messages[message_hash]['suggester']

        else:
            page = q.paginate(q.match(q.index("hash"), message_hash))
            ns = q.map_(lambda a: q.select(["data"], q.get(a)), page)
            result = client.query(ns)['data']
            if len(result) > 0:
                message = fill_line(result[0]['title'])
                suggester = result[0]['suggester']
            else:
                raise tornado.web.HTTPError(404)

        self.output_message(message, message_hash, suggester)
    
        image = Image.new("RGBA", (300, 150), (255,255,255))
        image_size = image.size

        # load the font and image
        font = ImageFont.truetype(fontFile, 18)
        # image = Image.open(imageFile)
        # firts you must prepare your text (you dont need this for english text)
        # text = unicode(message, "utf-8")
        text = message
        # start drawing on image
        draw = ImageDraw.Draw(image)

        lines = text_wrap(text, font, image_size[0] - 10)
        line_height = font.getsize('hg')[1]
        
        x = 10
        y = 20
        for line in lines:
            reshaped_text = arabic_reshaper.reshape(line)    # correct its shape
            bidi_text = get_display(reshaped_text)           # correct its direction
            # draw the line on the image
            x = image_size[0] - font.getsize(bidi_text)[0] - x
            draw.text((x, y), bidi_text, (0,0,0), font=font)

            # update the y position so that we can use it for next line
            y = y + line_height
            x = 10

        # draw.text((10, 0), bidi_text, (0,0,0), font=font)
        draw = ImageDraw.Draw(image)

        # save it
        image.save("thumbnails/{}.png".format(message_hash))

    def output_message(self, message, message_hash, suggester):
        self.render('index.html', message=message, message_hash=message_hash, suggester=suggester)

class SubjectHandler(tornado.web.RequestHandler):
    def get(self):
        self.render('add_subject.html')

    def post(self, *args, **kwargs):
        title = self.get_argument('subject')
        suggester = self.get_argument('suggester')
        resource = self.get_argument('resources')
        token = ''.join(random.choice('1234567890') for i in range(18))
        hashed = md5(title.encode('utf-8')).hexdigest()

        client.query(q.insert(q.ref(q.collection('Subjects'), token), 1, 'create', {'data' : {
            'title' : title,
            'suggester' : suggester,
            'hash' : hashed,
            'resource' : resource,
            'confirmed' : 'False'
        }}))

        self.write(hashed)


class PlainTextHandler(MainHandler):
    def output_message(self, message, message_hash, suggester):
        self.set_header('Content-Type', 'text/plain')
        self.write(xhtml_unescape(message).replace('<br/>', '\n'))

class JsonHandler(MainHandler):
    def output_message(self, message, message_hash, suggester):
        self.set_header('Content-Type', 'application/json')
        self.write(json.dumps({
            'hash': message_hash,
            'disc_subject':message.replace('\n', ''),
            'permalink': self.request.protocol + "://" + self.request.host + '/' + message_hash,
            'suggester': suggester
        }))

# class ThumbnailHandler(tornado.web.RequestHandler):
#     def get(self, img_id):
#         img_name = 'thumbnails/' + img_id + '.png'
#         img = pygame.image.load(img_name)
#         str_img = pygame.image.tostring(img, "RGB")
#         size = img.get_size()
#         fimg = Image.frombytes("RGB", size, str_img, "raw")
#         fobj = StringIO.StringIO()
#         fimg.save(fobj, format="png")  #jpeg encoder isn't available in my install...
#         for line in fobj.getvalue():
#             self.write(line)
#         self.set_header("Content-type",  "image/png")

settings = {
    'static_path': os.path.join(os.path.dirname(__file__), 'static'),
}

application = tornado.web.Application([
    (r'/', MainHandler),
    (r'/([a-z0-9]+)', MainHandler),
    (r'/subject/add', SubjectHandler),
    (r'/index.json', JsonHandler),
    (r'/([a-z0-9]+).json', JsonHandler),
    (r'/index.txt', PlainTextHandler),
    (r'/([a-z0-9]+)/index.txt', PlainTextHandler),
    (r'/thumbnails/(.*)', tornado.web.StaticFileHandler, {'path': os.path.join(os.path.dirname(__file__), 'thumbnails')})
    # (r'/thumbnails/([a-z0-9]+)', tornado.web.StaticFileHandler, {'path': os.path.join(os.path.dirname(__file__), 'thumbnails')}),
], **settings)

if __name__ == '__main__':
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(os.environ.get("PORT", 5002))
    tornado.ioloop.IOLoop.instance().start()
