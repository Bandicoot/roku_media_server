#!/usr/bin/env python
# Copyright 2010, Brian Taylor
# Distribute under the terms of the GNU General Public License
# Version 2 or better


# this file contains the configurable variables
config_file = "config.ini"

# main webapp
import os
import re
import web
from PyRSS2Gen import *
import eyeD3
import urllib
import ConfigParser
import math
from common import *

class RSSImageItem(RSSItem):
  "extending rss items to support our extended tags"
  TAGS = ('image', 'filetype', 'tracknum')
  def __init__(self, **kwargs):
    for name in RSSImageItem.TAGS:
      if name in kwargs:
        setattr(self, name, kwargs[name])
        del kwargs[name]
      else:
        setattr(self, name, None)

    RSSItem.__init__(self, **kwargs)

  def publish_extensions(self, handler):
    for name in RSSImageItem.TAGS:
      val = getattr(self, name)
      if val:
        handler.startElement(name, {})
        handler.characters(val)
        handler.endElement(name)

def file2item(fname, config, image=None):
  # guess the filetype based on the extension
  ext = os.path.splitext(fname)[1].lower()

  title = "None"
  description = "None"
  filetype = None
  mimetype = None
  tracknum = None

  if ext == ".mp3":
    # use the ID3 tags to fill out the mp3 data

    try:
      tag = eyeD3.Tag()
      if not tag.link(fname):
        return None
    except:
      print "library failed to parse ID3 tags for %s. Skipping." % fname
      return None

    title = tag.getTitle()
    description = tag.getArtist()
    
    tracknum = tag.getTrackNum()[0]
    if tracknum:
      tracknum = str(tracknum)


    filetype = "mp3"
    mimetype = "audio/mpeg"

  elif ext == ".wma":
    # use the filename as the title

    basename = os.path.split(fname)[1]
    title = os.path.splitext(basename)[0]
    description = ""
    filetype = "wma"
    mimetype = "audio/x-ms-wma"

  elif ext == ".m4v":
    # this is a video file

    basename = os.path.split(fname)[1]
    title = os.path.splitext(basename)[0]
    description = "Video"
    filetype = "mp4"
    mimetype = "video/mp4"

  else:
    # don't know what this is

    return None

  size = os.stat(fname).st_size
  music_base = config.get("config", "music_dir")
  path = relpath26(fname, music_base)
  link="%s/media?%s" % (server_base(config), urllib.urlencode({'name':to_utf8(path)}))

  if image:
    image = relpath26(image, music_base)
    image = "%s/media?%s" % (server_base(config), urllib.urlencode({'name':to_utf8(image)}))

  print link

  return RSSImageItem(
      title = title,
      link = link,
      enclosure = Enclosure(
        url = link,
        length = size,
        type = mimetype),
      description = description,
      guid = Guid(link, isPermaLink=0),
      pubDate = datetime.datetime.now(),
      image = image,
      filetype = filetype,
      tracknum = tracknum)

def dir2item(dname, config, image):
  music_base = config.get("config", "music_dir")
  path = relpath26(dname, music_base)

  link = "%s/feed?%s" % (server_base(config), urllib.urlencode({'dir':to_utf8(path)}))
  name = os.path.split(dname)[1]

  if image:
    image = relpath26(image, music_base)
    image = "%s/media?%s" % (server_base(config), urllib.urlencode({'name':to_utf8(image)}))

  description = "Folder"
  #if image:
  #  description += "<img src=\"%s\" />" % image

  return RSSImageItem(
      title = name,
      link = link,
      description = description,
      guid = Guid(link, isPermaLink=0),
      pubDate = datetime.datetime.now(),
      image = image)

def getart(path):
  curr_image = None
  img_re = re.compile(".jpg|.jpeg|.png")

  for base, dirs, files in os.walk(path):
    # don't recurse when searching for artwork
    del dirs[:]

    for file in files:
      ext = os.path.splitext(file)[1]
      if ext and img_re.match(ext):
        curr_image = os.path.join(base,file)
        break

  return curr_image

def to_unicode(obj, encoding='utf-8'):
  "convert to unicode if not already and it's possible to do so"

  if isinstance(obj, basestring):
    if not isinstance(obj, unicode):
      obj = unicode(obj, encoding)
  return obj

def to_utf8(obj):
  "convert back to utf-8 if we're in unicode"

  if isinstance(obj, unicode):
    obj = obj.encode('utf-8')
  return obj

def item_sorter(lhs, rhs):
  "folders first, sort on artist, then track number (prioritize those with), then track name"

  # folders always come before non folders
  if lhs.description == "Folder" and rhs.description != "Folder":
    return -1
  if rhs.description == "Folder" and lhs.description != "Folder":
    return 1

  # first sort by artist
  if lhs.description.lower() < rhs.description.lower():
    return -1
  if rhs.description.lower() < lhs.description.lower():
    return 1

  # things with track numbers always come first
  if lhs.tracknum and not rhs.tracknum:
    return -1
  if rhs.tracknum and not lhs.tracknum:
    return 1

  # if both have a track number, sort on that
  if lhs.tracknum and rhs.tracknum:
    if int(lhs.tracknum) < int(rhs.tracknum):
      return -1
    elif int(lhs.tracknum) > int(rhs.tracknum):
      return 1
  
  # if the track numbers are the same or both don't
  # exist then sort by title
  if lhs.title.lower() < rhs.title.lower():
    return -1
  elif rhs.title.lower() < lhs.title.lower():
    return 1
  else:
    return 0 # they must be the same

def is_letter(c):
  if c >= 'a' and c <= 'z':
    return True
  return False

def is_number(c):
  if c >= '0' and c <= '9':
    return True
  return False

def first_letter(str):
  return str[0].lower()

def partition_by_firstletter(subdirs, basedir, minmax, config):
  "based on config, change subdirs into alphabet clumps if there are too many"
  
  max_dirs = 10
  if config.has_option("config", "max_folders_before_split"):
    max_dirs = int(config.get("config", "max_folders_before_split"))

  # handle the trivial case
  if len(subdirs) <= max_dirs or max_dirs <= 0 or not minmax:
    return subdirs

  # figure out if we're doing a letter or number partition
  minl, maxl = minmax
  
  if is_letter(minl):
    min_of_class = 'a'
  elif is_number(minl):
    min_of_class = '0'
  else:
    # this must be a special character. give up
    return subdirs

  # presort
  subdirs.sort(key=lambda x: x.title.lower())

  # how many pivots? (round up)
  pivots = int(math.ceil(float(len(subdirs))/max_dirs))
  newsubdirs = []

  def get_letter(item):
    return first_letter(item.title)

  last_index_ord = len(subdirs) - 1
  last_end = 0

  # try to divide the list evenly
  for sublist in range(pivots):
    if last_end == last_index_ord:
      break # we're done

    last_letter = get_letter(subdirs[last_end])
    if last_end == 0:
      last_letter = minl

    next_end = min(last_end + max_dirs, len(subdirs) - 1)

    while get_letter(subdirs[next_end]) == last_letter and next_end != last_index_ord:
      next_end += 1

    first_unique = get_letter(subdirs[next_end])

    while get_letter(subdirs[next_end]) == first_unique and next_end != last_index_ord:
      next_end += 1

    next_letter = chr(max(ord(min_of_class), ord(get_letter(subdirs[next_end]))-1))
    if next_end == last_index_ord:
      next_letter = maxl

    # create the item
    link = "%s/feed?%s" % (server_base(config), urllib.urlencode({'dir':basedir, 'range': last_letter+next_letter}))

    newsubdirs.append(RSSImageItem(
      title = "%s - %s" % (last_letter.upper(), next_letter.upper()),
      link = link,
      description = "Folder",
      guid = Guid(link, isPermaLink=0)))

    last_end = next_end

  if len(newsubdirs) > 1:
    return newsubdirs
  else:
    return subdirs

def getdoc(path, dirrange, config, recurse=False):
  "get a media feed document for path"

  # make sure we're unicode
  path = to_unicode(path)

  number_subdirs = []
  letter_subdirs = []
  special_subdirs = []

  items = []

  if dirrange:
    minl, maxl = dirrange
    minl = minl.lower()
    maxl = maxl.lower()

  media_re = re.compile("\.mp3|\.wma|\.m4v")

  for base, dirs, files in os.walk(path):
    if not recurse:
      for dir in dirs:

        # skip directories not in our range
        first_chr = first_letter(dir)
        if dirrange and (first_chr < minl or first_chr > maxl):
          continue

        subdir = os.path.join(base,dir)
        item = dir2item(subdir, config, getart(subdir))
        if is_number(first_chr):
          number_subdirs.append(item)
        elif is_letter(first_chr):
          letter_subdirs.append(item)
        else:
          special_subdirs.append(item)

      del dirs[:]

    # first pass to find images
    curr_image = getart(base)

    for file in files:
      if not media_re.match(os.path.splitext(file)[1].lower()):
        print "rejecting %s" % file
        continue
      
      item = file2item(os.path.join(base,file), config, curr_image)
      if item:
        items.append(item)

  # include our partitioned folders
  if dirrange:
    # the range must either have only letters or only numbers
    if len(number_subdirs) > 0:
      items.extend(partition_by_firstletter(\
          number_subdirs, path, (minl,maxl), config))
    elif len(letter_subdirs) > 0:
      items.extend(partition_by_firstletter(\
          letter_subdirs, path, (minl,maxl), config))
  else:
    items.extend(partition_by_firstletter(number_subdirs, path, ('0','9'), config))
    items.extend(partition_by_firstletter(letter_subdirs, path, ('a','z'), config))

  items.extend(special_subdirs)

  # sort the items
  items.sort(item_sorter)
  music_base = config.get("config", "music_dir")

  if dirrange:
    range = "&range=%s" % (minl + maxl)
  else:
    range = ""

  doc = RSS2(
      title="A Personal Music Feed",
      link="%s/feed?dir=%s%s" % (server_base(config), relpath26(path, music_base), range),
      description="My music.",
      lastBuildDate=datetime.datetime.now(),
      items = items )

  return doc

def doc2m3u(doc):
  "convert an rss feed document into an m3u playlist"

  lines = []
  for item in doc.items:
    lines.append(item.link)
  return "\n".join(lines)

def range_handler(fname):
  "return all or part of the bytes of a fyle depending on whether we were called with the HTTP_RANGE header set"
  f = open(fname, "rb")

  bytes = None
  CHUNK_SIZE = 10 * 1024;

  # is this a range request?
  # looks like: 'HTTP_RANGE': 'bytes=41017-'
  if 'HTTP_RANGE' in web.ctx.environ:
    print "server issued range query: %s" % web.ctx.environ['HTTP_RANGE']

    # try a start only regex
    regex = re.compile('bytes=(\d+)-$')
    grp = regex.match(web.ctx.environ['HTTP_RANGE'])
    if grp:
      start = int(grp.group(1))
      print "player issued range request starting at %d" % start

      f.seek(start)

      # we'll stream it
      bytes = f.read(CHUNK_SIZE)
      while not bytes == "":
        yield bytes
        bytes = f.read(CHUNK_SIZE)

      f.close()

    # try a span regex
    regex = re.compile('bytes=(\d+)-(\d+)$')
    grp = regex.match(web.ctx.environ['HTTP_RANGE'])
    if grp:
      start,end = int(grp.group(1)), int(grp.group(2))
      print "player issued range request starting at %d and ending at %d" % (start, end)

      f.seek(start)
      bytes_remaining = end-start+1 # +1 because range is inclusive
      chunk_size = min(bytes_remaining, chunk_size)
      bytes = f.read(chunk_size)

      while not bytes == "":
        yield bytes

        bytes_remaining -= chunk_size
        chunk_size = min(bytes_remaining, chunk_size)
        bytes = f.read(chunk_size)

      f.close()
    
    # try a tail regex
    regex = re.compile('bytes=-(\d+)$')
    grp = regex.match(web.ctx.environ['HTTP_RANGE'])
    if grp:
      end = int(grp.group(1))
      print "player issued tail request beginning at %d from end" % end

      f.seek(-end, os.SEEK_END)
      bytes = f.read()
      yield bytes
      f.close()

  else:
    # write the whole thing
    # we'll stream it
    bytes = f.read(CHUNK_SIZE)
    while not bytes == "":
      yield bytes
      bytes = f.read(CHUNK_SIZE)
    
    f.close()

class MediaHandler:
  "retrieve a song"

  def GET(self):
    song = web.input(name = None)
    if not song.name:
      return

    config = parse_config(config_file)
    music_base = config.get("config", "music_dir")
    name = song.name
    name = os.path.join(music_base, name)

    # refuse anything that isn't in the media directory
    # IE, refuse anything containing pardir
    fragments = song.name.split(os.sep)
    if os.path.pardir in fragments:
      print "SECURITY WARNING: Someone was trying to access %s. The MyMedia client shouldn't do this" % song.name
      return

    size = os.stat(name).st_size

    # make a guess at mime type
    ext = os.path.splitext(os.path.split(name)[1] or "")[1].lower()

    if ext == ".mp3":
      web.header("Content-Type", "audio/mpeg")
    elif ext == ".wma":
      web.header("Content-Type", "audio/x-ms-wma")
    elif ext == ".m4v":
      web.header("Content-Type", "video/mp4")
    elif ext == ".jpg":
      web.header("Content-Type", "image/jpeg")
    else:
      web.header("Content-Type", "audio/mpeg")

    web.header("Content-Length", "%d" % size)
    return range_handler(name)

class RssHandler:
  def GET(self):
    "retrieve a specific feed"

    config = parse_config(config_file)
    collapse_collections = config.get("config", "collapse_collections").lower() == "true"

    web.header("Content-Type", "application/rss+xml")
    feed = web.input(dir = None, range=None)
    range = feed.range
    if range: range = tuple(range)

    if feed.dir:
      path = os.path.join(config.get("config", "music_dir"), feed.dir)
      return getdoc(path, range, config, collapse_collections).to_xml()
    else:
      return getdoc(config.get("config", 'music_dir'), range, config).to_xml()

class M3UHandler:
  def GET(self):
    "retrieve a feed in m3u format"

    config = parse_config(config_file)

    web.header("Content-Type", "text/plain")
    feed = web.input(dir = None)
    if feed.dir:
      path = os.path.join(config.get("config", "music_dir"), feed.dir)
      return doc2m3u(getdoc(path, config, True))
    else:
      return doc2m3u(getdoc(config.get("config", 'music_dir'), config, True))

urls = (
    '/feed', 'RssHandler',
    '/media', 'MediaHandler',
    '/m3u', 'M3UHandler')

app = web.application(urls, globals())

if __name__ == "__main__":
  import sys

  config = parse_config(config_file)

  sys.argv.append(config.get("config","server_port"))
  app.run()
