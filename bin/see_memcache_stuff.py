#!/usr/bin/python
"""
Memcache status reporting and monitoring script

Uses a django settings file if it can, failing silently if it's not found.

Requirements:
    py-memcached >= 1.4

Optional Requirements:
    django settings file with CACHE_BACKEND properly setup for memcache
    I.E. 
        CACHE_BACKEND = "memcached://<server1>:<port1>;<server2>:<port2>/"

Features:

* easy nagios integration
* monitors multipule hosts (with django settings file setup)
* can be used on a terminal to dsiplay interesting stats for a memcache server-farm
* colorized information display (use -c flag)

Example Usage:

Non-nagios usage:
    me@MyComputer:~$ python see_memcache_stuff.py -H localhost -g -r
    MemCache status for localhost
    56 items using 2131956 of 67108864
     3.18% full
    3 connections being handled
get rate: 50.5 % hit rate: 75.5 %

Nagios usage:
    me@MyComputer:~$ python see_memcache_stuff.py -H localhost -n
    CHECKMEMCACHE OK:  3.18% full on localhost 
"""

import memcache
import re
import sys
try:
    from django.conf import settings
    IMPORTED_SETTINGS = True
except:
    IMPORTED_SETTINGS = False
from optparse import OptionParser,OptionGroup

class CacheServerUnavailable(Exception):
    pass


RETURN_OK = 0
RETURN_WARNING = 1
RETURN_CRITICAL = 2
RETURN_UNKNOWN = 3 # hopefully never used... EVER
RETURN_FAILED = RETURN_WARNING # default failure is a warning
STYLE = {
            "default"    :     "\033[m",
            "black"      :     "\033[30m", 
            "red"        :     "\033[31m",
            "green"      :     "\033[32m",
            "yellow"     :     "\033[33m",
            "blue"       :     "\033[34m",
            "magenta"    :     "\033[35m",
            "cyan"       :     "\033[36m",
            "white"      :     "\033[37m",}

DEFAULT_STYLE='yellow'

class PrintHelper(object):
    def __init__(self,stats,options,host):
        self.stats = stats
        self.items = int(self.stats[ 'curr_items' ])
        self.bytes = int( self.stats[ 'bytes' ] )
        self.limit_maxbytes = int( self.stats[ 'limit_maxbytes' ] ) or bytes
        self.current_conns = int( self.stats[ 'curr_connections' ] )
        self.cache_host = host.split(":")[0]
        self.cache_port = host.split(":")[1]
        self.precent_full = ( 100.0 * self.bytes / self.limit_maxbytes )
        self.colorize = options.colorize
        self.verbose = options.verbose
        self.nagios = options.nagios
        self.get_rate = options.get_rate
        self.hit_rate = options.hit_rate
        self.banner = options.banner
        self.options = options
    
    def get_getrate(self):
        cmdget = int( self.stats['cmd_get'] )
        cmdset = int( self.stats['cmd_set'] )
        try:
            getrate = ( (cmdget) * 100) / (cmdget + cmdset)
            dsp_getrate = getrate + 0.5
        except ZeroDivisionError:
            return [0, 0]
        return [dsp_getrate, getrate]
    
    def get_hitrate(self):
        hits = int( self.stats['get_hits'])
        misses = int( self.stats['get_misses'])
        if hits ==0 and misses == 0:
            return [0, 0]
        if hit_sum == 0:
            hitrate = 0
        else:
            hitrate = hit_sum
        dsp_hitrate = hitrate + 0.5
        return [dsp_hitrate, hitrate]
    


def print_status_report(ph):
    print_hitrate, hitrate = ph.get_hitrate()
    print_getrate, getrate = ph.get_getrate()
    rate_str_c = "%s rate: " + STYLE['yellow'] + "%s %%" + STYLE['default']
    rate_str_red = "%s rate: "+ STYLE['red'] +"%s %%" + STYLE['default']
    rate_str = "%s rate: %s %%"

    if not ph.nagios:
        if ph.banner:
            print "------------------------------------------------"
        if ph.colorize:
            print "MemCache status for %s%s%s" % (STYLE['green'], ph.cache_host, STYLE['default'] )
            print "%s%d%s items using %s%d%s of%s%d%s" % ( STYLE['yellow'], ph.items, STYLE['default'], STYLE['yellow'], ph.bytes,STYLE['default'], STYLE['yellow'], ph.limit_maxbytes, STYLE['default'] )
            print "%s%5.2f%%%s full" % (STYLE['yellow'], ph.precent_full, STYLE['default'] )
            print "%s%d%s connections being handled" % ( STYLE['yellow'], ph.current_conns, STYLE['default'] )
            if ph.get_rate:
                if ph.hit_rate:
                    if hitrate < 50.5:
                        print rate_str_red% ( 'hit', print_hitrate ),
                    else:
                        print rate_str_c% ( 'hit', print_hitrate ),
                if getrate < 50.5:
                    print rate_str_red% ( 'get', print_getrate )
                else:
                    print rate_str_c %('get', print_getrate)
            if ph.hit_rate and not ph.get_rate:
                if hitrate < 50.5:
                    print rate_str_red% ( 'hit', print_hitrate )
                else:
                    print rate_str_c% ( 'hit', print_hitrate )
        else:
            print "MemCache status for %s" % ( ph.cache_host )
            print "%d items using %d of %d" % ( ph.items, ph.bytes, ph.limit_maxbytes )
            print "%5.2f%% full %d connections being handled" % ( ph.precent_full, ph.current_conns )
            if ph.get_rate:
                getrate_str = rate_str % ( 'get', print_getrate )
                if ph.hit_rate:
                    print getrate_str,
                else:
                    print getrate_str
            if ph.hit_rate:
                hitrate_str = rate_str % ( 'hit', print_hitrate )
                print hitrate_str
    else:
        nagios_line = "CHECKMEMCACHE OK"
        if ph.hit_rate:
            nagios_line = "%s get rate: %s" %(nagios_line, print_getrate)
            #print "CHECKMEMCACHE OK hit rate: %s %%|getrate=%s"%(print_hitrate, hitrate)
        if ph.get_rate:
            nagios_line = "%s hit rate: %s" %(nagios_line, print_hitrate)
            #print "CHECKMEMCACHE OK hit rate: %s %%|hitrate=%s"%(print_getrate, getrate)
        nagios_line = "%s %5.2f%% full on %s "% ( nagios_line, ph.precent_full, ph.cache_host )
            #print "CHECKMEMCACHE OK: %5.2f%% full on %s " % ( ph.precent_full, ph.cache_host )
        print nagios_line


def show_memcache_servers(options,server='NONE'):
    if not options.nagios:
        try:
            if IMPORTED_SETTINGS:
                if not settings.CACHE_BACKEND.startswith( 'memcached://' ):
                    print "CHECKMEMCACHE CRITICAL: No django setup for memcached"
        except:
            print "No server specified and/or django is not installed"
            return RETURN_UNKNOWN
    if server == 'NONE':
        if options.nagios:
            print "CHECKMEMCACHE CRITICAL: No server specified!"
            return RETURN_WARNING
        if IMPORTED_SETTINGS:
            server = settings.CACHE_BACKEND
        else:
            print "CHECKMEMCACHE CRITICAL: could not import django settings file!"
            return RETURN_WARNING
    m = re.search( r'//(.+:\d+)', server )
    hosts =  m.group(1)
    code_list = []
    if ";" in hosts:
        for cache_host in hosts.split(";"):
            code_list.append(check_connection(m, cache_host ,options))
    else:
        return check_connection(m, hosts, options)
    current_code = RETURN_OK
    if code_list:
        for code in code_list:
            if code > current_code:
                current_code = code
        return current_code
    else:
        return RETURN_OK


def check_connection(m, cache_host, options):
    try:
        h = memcache.Client([cache_host,])
    except:
        print "CHECKMEMCACHE CRITICAL: memcached server down!"
        return RETURN_CRITICAL
    try:
        stats = h.get_stats()
        h.disconnect_all()
    except:
        print "CHECKMEMCACHE CRITICAL: could not read/write memcache server!"
        return RETURN_CRITICAL
        
    ph = PrintHelper(stats[0][1], options, cache_host) # helper for stats.
    if options.verbose:
        print stats
    print_status_report(ph)
    return RETURN_OK
    

def main():
    usage = """usage: %prog -cHnPgrvb"""
    version="%prog 0.1"
    parser = OptionParser(usage=usage, version="%prog 0.1")
    
    group = OptionGroup(parser, "Nagios Settings","These settings are required for this script to be used by nagios")
    group.add_option('-n', dest='nagios', action='store_true', default=False, help='makes nagios compatible output.')
    group.add_option('-H', '--host', dest='host', nargs=1, default=None, help='host to check')    
    group.add_option('-P', '--port', dest='port', nargs=1, default=11211, help = 'port to use [default %default]')
    
    parser.add_option_group(group)
    parser.add_option('-c', '--colorize', dest='colorize', action='store_true', default=False, help='colorizes output for terminals with color')
    parser.add_option('-g', '--get_rate', dest='get_rate', action='store_true', default=False, help='retreive current get rate for memcache')
    parser.add_option('-r', '--hit_rate', dest='hit_rate', action='store_true', default=False, help='retreive current hit rate for memcache')
    parser.add_option('-v', '--verbose', dest='verbose', action='store_true', default=False, help='verbose mode, shows various memcached values')
    parser.add_option('-b', '--no-banner', dest='banner', action='store_false', default=True, help='show banners on the top of each entry [default %default]')
    
    (options, args) = parser.parse_args()
    if args:
        try:
            server = "memcached://%s/"%(args[0])
        except:
            server = 'NONE'
    elif options.host and options.port:
        server = "memcached://%s:%s/"%(options.host, options.port)
    else:
        server='NONE'
    
    return show_memcache_servers(options, server)

if __name__ == '__main__':
    sys.exit(main())