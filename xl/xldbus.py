# Copyright (C) 2008-2009 Adam Olsen 
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.

from xl.nls import gettext as _
import logging
import dbus, dbus.service, gobject, sys
from optparse import OptionParser

logger = logging.getLogger(__name__)

def check_dbus(bus, interface):
    obj = bus.get_object('org.freedesktop.DBus', '/org/freedesktop/DBus')
    dbus_iface = dbus.Interface(obj, 'org.freedesktop.DBus')
    avail = dbus_iface.ListNames()
    return interface in avail

def check_exit(options, args):
    """
        Check to see if dbus is running, and if it is, call the appropriate
        methods
    """
    iface = False
    exaile = None
    if not options.new:
        # TODO: handle dbus stuff
        bus = dbus.SessionBus()
        if check_dbus(bus, 'org.exaile.ExaileInterface'):
            remote_object = bus.get_object('org.exaile.ExaileInterface', 
                '/org/exaile')
            iface = dbus.Interface(remote_object,
                'org.exaile.ExaileInterface')
            iface.test_service('testing dbus service')
            exaile = remote_object.exaile

            # Assume that args are files to be added to the current playlist.
            # This enables:    exaile PATH/*.mp3
            if args:
                # if '-' is the first argument then we look for a newline 
                # separated list of filenames from stdin.
                # This enables:    find PATH -name *.mp3 | exaile -
                if args[0] == '-':
                    args = sys.stdin.read().split('\n')
                iface.enqueue(args)
            
    if not iface:
        return False

    comm = False
    info_commands = (
            'get_artist', 
            'get_title', 
            'get_album',
            'get_length', 
            'get_rating'
            )

    playing = iface.is_playing()
    for command in info_commands:
        if getattr(options, command):
            comm = True
            if not playing:
                print "Not playing."
                break
            else:
                print iface.get_track_attr(command.replace('get_', ''))

    modify_commands = (
           'set_rating',
           )

    for command in modify_commands:
        value = getattr(options, command)
        if value:
            iface.set_track_attr(command, value)
            comm = True

    volume_commands = (
            'inc_vol',
            'dec_vol',
            )

    for command in volume_commands:
        value = getattr(options, command)
        if value:
            iface.change_volume(command.replace('_vol', ''), value)

    run_commands = (
            'play', 
            'stop', 
            'next', 
            'prev', 
            'play_pause',
            )
    for command in run_commands:
        if getattr(options, command):
            getattr(iface, command)()
            comm = True

    query_commands = (
            'current_position',
            'get_volume',
            )

    for command in query_commands:
        if getattr(options, command):
            print getattr(iface, command)()
            comm = True

    to_implement = (
            'query',
            'guiquery',
            )
    for command in to_implement:
        if getattr(options, command):
            logger.warning("FIXME: command not implemented")
            comm = True

    return True

class DbusManager(dbus.service.Object):
    """
        The dbus interface object for Exaile
    """
    def __init__(self, exaile):
        """
            Initilializes the interface
        """
        self.exaile = exaile
        self.bus = dbus.SessionBus()
        self.bus_name = dbus.service.BusName('org.exaile.ExaileInterface',
            bus=self.bus)
        dbus.service.Object.__init__(self, self.bus_name, "/org/exaile")

    @dbus.service.method('org.exaile.ExaileInterface', 's')
    def test_service(self, arg):
        """
            Just test the dbus object
        """
        logger.debug(arg)

    @dbus.service.method('org.exaile.ExaileInterface', None, 'b')
    def is_playing(self):
        """
            Returns True if Exaile is playing (or paused), False if it's not
        """

        if self.exaile.player.current: return True
        else: return False

    @dbus.service.method('org.exaile.ExaileInterface', 's')
    def get_track_attr(self, attr):
        """
            Returns a attribute of a track
        """
        try:
            value = self.exaile.player.current[attr]
        except ValueError:
            value = None
        except TypeError:
            value = None

        if value:
            if type(value) == list:
                return u"\n".join(value)
            return unicode(value)
        return u''

    @dbus.service.method("org.exaile.ExaileInterface", 'sv')
    def set_track_attr(self, attr, value):
        """
            Sets rating of a track
        """
        try:
            set_attr = getattr(self.exaile.player.current, attr)
            set_attr(value)
        except AttributeError:
            pass
        except TypeError:
            pass

    @dbus.service.method("org.exaile.ExaileInterface", 'si')
    def change_volume(self, action, value):
        """
            Increases the volume by percentage
        """
        vol = self.exaile.player.get_volume()
        if action == 'inc':
            vol += value
        elif action == 'dec':
            vol -= value
        self.exaile.player.set_volume(vol)

    @dbus.service.method("org.exaile.ExaileInterface")
    def prev(self):
        """
            Jumps to the previous track
        """
        self.exaile.queue.prev()

    @dbus.service.method("org.exaile.ExaileInterface")
    def stop(self):
        """
            Stops playback
        """
        self.exaile.player.stop()

    @dbus.service.method("org.exaile.ExaileInterface")
    def next(self):
        """
            Jumps to the next track
        """
        self.exaile.queue.next()

    @dbus.service.method("org.exaile.ExaileInterface")
    def play(self):
        """
            Starts playback
        """
        self.exaile.queue.play()

    @dbus.service.method("org.exaile.ExaileInterface")
    def play_pause(self):
        """
            Toggle Play or Pause
        """
        self.exaile.player.toggle_pause()

    @dbus.service.method("org.exaile.ExaileInterface", None, "s")
    def current_position(self):
        """
            Returns the position inside the current track as a percentage
        """
        progress = self.exaile.player.get_progress()
        if progress == -1:
            return ""
        return "%d%%" % (progress * 100)

    @dbus.service.method("org.exaile.ExaileInterface", None, "s")
    def get_volume(self):
        """
            Returns the current volume level as percentage
        """
        vol = self.exaile.player.get_volume()
        return "%d%%" % vol

    @dbus.service.method("org.exaile.ExaileInterface", None, "s")
    def get_version(self):
        return self.exaile.get_version()

    @dbus.service.method("org.exaile.ExaileInterface", "s")
    def play_file(self, filename):
        """
            Plays the specified file
        """
        self.exaile.gui.open_uri(filename)

    @dbus.service.method("org.exaile.ExaileInterface", "as")
    def enqueue(self, filenames):
        """
            Adds the specified files to the current playlist
        """
        from xl import track  # do this here to avoid loading 
                              # settings when issuing dbus commands
        # FIXME: Get rid of dependency on xlgui
        #        by moving sorting column somewhere else
        pl = self.exaile.gui.main.get_selected_playlist()
        column, descending = pl.get_sort_by()
        tracks = []

        for file in filenames:
            tracks.extend(track.get_tracks_from_uri(file))

        tracks.sort(key=lambda track: track.sort_param(column), reverse=descending)
        self.exaile.queue.current_playlist.add_tracks(tracks)

        if not self.exaile.player.is_playing():
            try:
                self.exaile.queue.play(tracks[0])
            except IndexError:
                pass

