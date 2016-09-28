#!/usr/bin/env python
#
# Google appengine app that crawls data from the LittleField simulation
# and puts it together into HTML or CSV format.
# 
# All you have to do is update your user name password and run the app.

import csv
import jinja2
import os
import re
import string
import StringIO
import urllib
import webapp2

from google.appengine.api import urlfetch

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

class Session():
    USER=''
    PASS=''

    def __init__(self):
        self.cookie = ''
        self.data = {}
        self.standing = []

    def headers(self):
        return {'Cookie': self.cookie}

    def fields(self):
        return ['Day',
                'Real Time',
                'Job Arrivals',
                'Queue Jobs',
                'Station 1 Queue',
                'Station 1 Utilization',
                'Station 2 Queue',
                'Station 2 Utilization',
                'Station 3 Queue',
                'Station 3 Utilization',
                'Completed Jobs 1',
                'Completed Jobs 2',
                'Completed Jobs 3',
                'Lead Times 1',
                'Lead Times 2',
                'Lead Times 3',
                'Revenue 1',
                'Revenue 2',
                'Revenue 3',
                'Total Revenue',
                'Rolling Revenue Avg >50d',
                'Total Completed Jobs',
                'Inventory',
                'Cash']

    def average_revenue(self):
      revenue = 0
      n = 0
      for r in self.data:
          if r > 50:
              revenue += self.data[r]['Total Revenue']
              n += 1
      return float(revenue) / n

    def Login(self):
        result = urlfetch.fetch(
            'http://sim.responsive.net/Littlefield/CheckAccess',
            payload=urllib.urlencode({
                'id': self.USER,
                'password': self.PASS,
                'institution': 'feldman',
            }),
            method=urlfetch.POST)
        self.cookie = result.headers.get('set-cookie')

    def ParseStanding(self):
        response = urlfetch.fetch(
            'http://sim.responsive.net/Littlefield/Standing',
            headers=self.headers())
        data = []
        for m in re.finditer("<font face=arial>([^<]+)</font>",
                             response.content):
            data.append(m.group(1).strip())

        self.standing = []
        for pos, team, cash in zip(data[0::3], data[1::3], data[2::3]):
            self.standing.append((pos, team, cash))

    def _ParseMulti(self, url, prefix):
        response = urlfetch.fetch(
            'http://sim.responsive.net/Littlefield' + url,
            headers=self.headers())
            
        for m in re.finditer("{label: '(\d+)', points: '([^']+)'}", response.content):
            t = prefix + m.group(1)
            data = string.split(m.group(2), ' ')
            for day, r in zip(data[0::2], data[1::2]):
                try:
                    self.data.setdefault(int(day), {'Day': day})[t] = r
                except:
                    pass

    def _ParseSingle(self, url, prefix):
        response = urlfetch.fetch(
            'http://sim.responsive.net/Littlefield' + url,
            headers=self.headers())
        for m in re.finditer("{label: 'data', points: '([^']+)'}", response.content):
            data = string.split(m.group(1), ' ')
            for day, quantity in zip(data[0::2], data[1::2]):
                try:
                    self.data.setdefault(int(day), {'Day': day})[prefix] = quantity
                except:
                    pass

    def ParseInventory(self):
        self._ParseSingle('/Plot1?data=INV&plottech=html5',
                          'Inventory')

    def ParseDemand(self):
        self._ParseSingle('/Plot1?data=JOBIN&plottech=html5',
                          'Job Arrivals')

    def ParseQueueJobs(self):
        self._ParseSingle('/Plot1?data=JOBQ&plottech=html5',
                          'Queue Jobs')

    def ParseRevenue(self):
        self._ParseMulti('/Plotk?data=JOBREV&sets=3&plottech=html5',
                         'Revenue ')
        for k, v in self.data.iteritems():
            v['Total Revenue'] = round(float(v['Revenue 1']) +
                                       float(v['Revenue 2']) +
                                       float(v['Revenue 3']), 2)
        n = 0
        s = 0
        for d in sorted(self.data):
            if d > 50:
                n += 1
                s += self.data[d]['Total Revenue']
                self.data[d]['Rolling Revenue Avg >50d'] = round(s / float(n), 2)

    def ParseLeadTimes(self):
        self._ParseMulti('/Plotk?data=JOBT&x=all',
                         'Lead Times ')

    def ParseStationUtilization(self, station):
        self._ParseSingle('/Plot1?data=S%dUTIL&plottech=html5' % station,
                          'Station %d Utilization' % station)

    def ParseStationQueue(self, station):
        self._ParseSingle('/Plot1?data=S%dQ&plottech=html5' % station,
                          'Station %d Queue' % station)

    def ParseCompletedJobs(self):
        self._ParseMulti('/Plotk?data=JOBOUT&x=all',
                         'Completed Jobs ')
        for k, v in self.data.iteritems():
            v['Total Completed Jobs'] = sum([v['Completed Jobs 1'],
                                             v['Completed Jobs 2'],
                                             v['Completed Jobs 3']])

    def ParseCash(self):
        self._ParseSingle('/Plot1?data=CASH&plottech=html5',
                          'Cash')


class MainHandler(webapp2.RequestHandler):
    def get(self):
        s = Session()
        s.Login()
        s.ParseCompletedJobs()        
        s.ParseRevenue()
        s.ParseInventory()
        s.ParseLeadTimes()
        s.ParseDemand()
        s.ParseQueueJobs()

        s.ParseStationUtilization(1)
        s.ParseStationUtilization(2)
        s.ParseStationUtilization(3)

        s.ParseStationQueue(1)
        s.ParseStationQueue(2)
        s.ParseStationQueue(3)

        s.ParseCash()
        s.ParseStanding()

        t = self.request.get('t', default_value='html')
        if t == 'csv':
            out = StringIO.StringIO()
            w = csv.DictWriter(out, fieldnames=s.fields())
            w.writeheader()
            for p in sorted(s.data):
                w.writerow(s.data[p])
            self.response.headers.add_header('Content-Type', 'text/csv')
            self.response.write(out.getvalue())
        else:            
            template = JINJA_ENVIRONMENT.get_template('index.html')
            self.response.write(template.render({
                'data': s.data,
                'team': s.USER,
                'standing': s.standing,
                'avg_revenue': s.average_revenue(),
                'fields': s.fields()}))

app = webapp2.WSGIApplication([
    ('/', MainHandler)
], debug=True)
