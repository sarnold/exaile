import gtk, gobject
from xl import event, common, playlist
from xl import track
from xl.nls import gettext as _
from xlgui import panel, main, commondialogs
from xlgui import guiutil
from xl import xdg
import xlgui, os, os.path
import _feedparser as fp
import traceback

# set up logger
import logging
logger = logging.getLogger(__name__)

PODCASTS = None
CURPATH = os.path.realpath(__file__)
BASEDIR = os.path.dirname(CURPATH)

try:
    import hashlib
    md5 = hashlib.md5
except ImportError:
    import md5
    md5 = md5.new

def enable(exaile):
    if exaile.loading:
        event.add_callback(exaile_ready, 'gui_loaded')
    else:
        exaile_ready(None, exaile, None)

def exaile_ready(event, exaile, nothing):
    global PODCASTS

    if not PODCASTS:
        PODCASTS = PodcastPanel(main.mainwindow().window)
        controller = xlgui.controller()
        controller.panels['podcasts'] = PODCASTS
        controller.add_panel(*PODCASTS.get_panel())

def disable(exaile):
    global PODCASTS
    
    if PODCASTS:
        conroller = xlgui.controller()
        conroller.remove_panel(PODCASTS.get_panel()[0])
        PODCASTS = None

class PodcastPanel(panel.Panel):
    gladeinfo = ('file://' + os.path.join(BASEDIR, 'podcasts.glade'), 
        'PodcastPanelWindow')

    def __init__(self, parent):
        panel.Panel.__init__(self, parent, _('Podcasts'))
        self.podcasts = []
        self.podcast_playlists = playlist.PlaylistManager(
            'podcast_plugin_playlists')
        
        self._setup_widgets()
        self._connect_events()
        self.podcast_file = os.path.join(xdg.get_plugin_data_dir(),
            'podcasts_plugin.db') 
        self._load_podcasts()

    def _setup_widgets(self):
        self.model = gtk.ListStore(str, str)
        self.tree = self.xml.get_widget('podcast_tree')
        self.tree.set_model(self.model)

        text = gtk.CellRendererText()
        self.column = gtk.TreeViewColumn(_('Podcast'))
        self.column.pack_start(text, True)
        self.column.set_expand(True)
        self.column.set_attributes(text, text=0)
        self.tree.append_column(self.column)

        self.status = self.xml.get_widget('podcast_statusbar')

        self.menu = guiutil.Menu()
        self.menu.append(_('Refresh Podcast'), self._on_refresh, 'gtk-refresh')
        self.menu.append(_('Delete'), self._on_delete, 'gtk-delete')

    @guiutil.idle_add()
    def _set_status(self, message, timeout=0):
        self.status.set_text(message)

        if timeout:
            gobject.timeout_add(timeout, self._set_status, _('Idle.'), 0)

    def _connect_events(self):
        self.xml.signal_autoconnect({
            'on_add_button_clicked': self.on_add_podcast,
        })

        self.tree.connect('row-activated', self._on_row_activated)
        self.tree.connect('button-press-event', self._on_button_press)

    def _on_button_press(self, button, event):
        if event.button == 3:
            self.menu.popup(event)

    def _on_refresh(self, *e):
        (url, title) = self.get_selected_podcast()
        self._parse_podcast(url)

    def _on_delete(self, *e):
        (url, title) = self.get_selected_podcast()
        for item in self.podcasts:
            (title, _url) = item
            if _url == url:
                self.podcasts.remove(item)
                self.podcast_playlists.remove_playlist(md5(url).hexdigest())
                break

        self._save_podcasts()
        self._load_podcasts()

    def on_add_podcast(self, *e):
        dialog = commondialogs.TextEntryDialog(_('Enter the URL of the '
            'podcast to add'), _('Open Podcast'))
        dialog.set_transient_for(self.parent)
        dialog.set_position(gtk.WIN_POS_CENTER_ON_PARENT)

        result = dialog.run()
        dialog.hide()

        if result == gtk.RESPONSE_OK:
            url = dialog.get_value()
            self._parse_podcast(url, True)

    def get_selected_podcast(self):
        selection = self.tree.get_selection()
        (model, iter) = selection.get_selected()

        url = self.model.get_value(iter, 1)
        title = self.model.get_value(iter, 0)
        return (url, title)

    def _on_row_activated(self, *e):
        (url, title) = self.get_selected_podcast()

        try:
            pl = self.podcast_playlists.get_playlist(md5(url).hexdigest())
            self._open_podcast(pl, title)
        except ValueError:
            self._parse_podcast(url)

    @common.threaded
    def _parse_podcast(self, url, add_to_db=False):
        try:
            url = url.replace('itpc://', 'http://')

            self._set_status(_('Loading %s...') % url)
            d = fp.parse(url)
            entries = d['entries']

            title = d['feed']['title']

            if add_to_db:
                self._add_to_db(url, title)

            pl = playlist.Playlist(md5(url).hexdigest())

            tracks = []
            for e in entries:
                tr = track.Track()
                tr.set_loc(e['enclosures'][0].href)
                date = e['updated_parsed']
                tr['artist'] = title
                tr['title'] = e['title']
                tr['date'] = "%d-%02d-%02d" % (date.tm_year, date.tm_mon,
                    date.tm_mday)
                tracks.append(tr)
            
            pl.add_tracks(tracks)
            self._set_status('Idle.')

            self._open_podcast(pl, title)
            self.podcast_playlists.save_playlist(pl, overwrite=True)
        except:
            traceback.print_exc()
            self._set_status(_('Error loading podcast.'), 2000)

    @guiutil.idle_add()
    def _add_to_db(self, url, title):
        self.podcasts.append((title, url))
        self._save_podcasts()
        self._load_podcasts()

    @guiutil.idle_add()
    def _open_podcast(self, pl, title):
        new_pl = playlist.Playlist(title)
        new_pl.add_tracks(pl.get_tracks())
        main.mainwindow().add_playlist(new_pl)

    @common.threaded
    def _load_podcasts(self):
        self._set_status(_("Loading Podcasts..."))
        try:
            h = open(self.podcast_file)

            lines = (line.strip() for line in h.readlines())
            h.close()
            self.podcasts = []

            for line in lines:
                (url, title) = line.split('\t')
                self.podcasts.append((title, url))
        except (IOError, OSError):
            logger.info('WARNING: could not open podcast file')
            self._set_status(_('Idle.'))
            return

        self._done_loading_podcasts()

    @guiutil.idle_add()
    def _done_loading_podcasts(self):
        self.model.clear()
        self.podcasts.sort()
        for (title, url) in self.podcasts:
            self.model.append([title, url])

        self._set_status(_('Idle.'))

    def _save_podcasts(self):
        try:
            h = open(self.podcast_file, 'w')
        except (OSError, IOError):
            commondialogs.error(self.parent, _('Could not save podcast file'))
            return

        for (title, url) in self.podcasts:
            h.write('%s\t%s\n' % (url, title))

        h.close()
