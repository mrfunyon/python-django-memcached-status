Memcache status reporting and monitoring script
========

Uses a django settings file if it can, failing silently if it's not found.

Requirements:
---------------------------
 * py-memcached >= 1.4

Optional Requirements:
    django settings file with CACHE_BACKEND properly setup for memcache

Features:
---------------------------
* easy nagios integration
* monitors multipule hosts (with django settings file setup)
* can be used on a terminal to dsiplay interesting stats for a memcache server-farm
* colorized information display (use -c flag)

Example Usage:
---------------------------

Non-nagios usage:

    me@MyComputer:~$ python bin/see_memcache_stuff.py -H localhost -g -r
    MemCache status for localhost
    56 items using 2131956 of 67108864
    3.18% full
    3 connections being handled
    get rate: 50.5 % hit rate: 75.5 %

Nagios usage:

    me@MyComputer:~$ python bin/see_memcache_stuff.py -H localhost -n
    CHECKMEMCACHE OK:  3.18% full on localhost 
