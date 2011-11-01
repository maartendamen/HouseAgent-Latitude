import urllib
from twisted.web.client import getPage
from twisted.internet.defer import inlineCallbacks
from twisted.internet import reactor, task, defer
from math import sin, cos, atan2, sqrt, pi
import json, pickle
import datetime
from houseagent.plugins import pluginapi
import ConfigParser

class LatitudeWrapper():
    def __init__(self):
        
        callbacks = {'custom': self.cb_custom}
        self.pluginapi = pluginapi.PluginAPI('547b0e75-2cc2-484b-88ba-aa53742b0b8f', 'Latitude', **callbacks)

        self.get_accounts()        
        self.get_locations()
        self.latitude = Latitude(self)

        task.deferLater(reactor, 1.0, self.pluginapi.ready)

    def get_locations(self):
        self.locations = {}
        config = ConfigParser.RawConfigParser()
        config.read('latitude.conf')
        locations = config._sections['locations']

        for key, item in locations.iteritems():
            if key == '__name__': continue    
            self.locations[key] = pickle.loads(item)    

    def get_accounts(self):
        self.accounts = []
        config = ConfigParser.RawConfigParser()
        config.read('latitude.conf')
        accounts = config._sections['accounts']

        for key, item in accounts.iteritems():
            if key == '__name__': continue
            data = pickle.loads(item)
            # Add account to list
            acc = LatitudeAccount(key, data[1], data[0])
            acc.refreshtime = data[2]
            acc.proximity = data[3]
            self.accounts.append(acc)

    def cb_custom(self, action, parameters):
        
        print action, parameters
        
        # Location management
        if action == 'get_locations':
            d = defer.Deferred()
            d.callback(self.locations)
            return d
        
        elif action == 'add_location':
            config = ConfigParser.RawConfigParser()
            config.read('latitude.conf')            
            config.set('locations', parameters['name'], pickle.dumps(parameters['coordinates']))
            
            with open('latitude.conf', 'wb') as configfile:
                config.write(configfile)
                
            # reload locations
            self.get_locations()
            
            d = defer.Deferred()
            d.callback('OK')
            return d
        
        elif action == 'del_location':
            config = ConfigParser.RawConfigParser()
            config.read('latitude.conf')   
            config.remove_option('locations', parameters)
            
            with open('latitude.conf', 'wb') as configfile:
                config.write(configfile)
                
            # reload locations
            self.get_locations()
                
            d = defer.Deferred()
            d.callback('OK')
            return d
        
        elif action == 'edit_location':
            config = ConfigParser.RawConfigParser()
            config.read('latitude.conf')
            
            if parameters['id'] == parameters['name']:
                config.set('locations', parameters['name'], pickle.dumps(parameters['coordinates']))
            else:
                # new name
                config.remove_option('locations', parameters['id'])
                config.set('locations', parameters['name'], pickle.dumps(parameters['coordinates']))
                
            with open('latitude.conf', 'wb') as configfile:
                config.write(configfile)
                
            # reload locations
            self.get_locations()
                
            d = defer.Deferred()
            d.callback('OK')
            return d
        
        # Account management
        elif action == 'add_account':
            config = ConfigParser.RawConfigParser()
            config.read('latitude.conf')            
            config.set('accounts', parameters['name'], pickle.dumps(parameters['details']))
            
            with open('latitude.conf', 'wb') as configfile:
                config.write(configfile)
                
            # reload accounts
            self.get_accounts()
            
            # restart tasks
            self.latitude.restart_update_tasks()
            
            d = defer.Deferred()
            d.callback('OK')
            return d
        elif action == 'get_accounts':
            accounts = {}
            for acc in self.accounts:
                accounts[acc.username] = [acc.device_id, acc.password, acc.refreshtime, acc.proximity, acc.latitude, acc.longitude, str(acc.lastupdate)]
            d = defer.Deferred()
            d.callback(accounts)
            return d
        
        elif action == 'del_account':
            config = ConfigParser.RawConfigParser()
            config.read('latitude.conf')   
            config.remove_option('accounts', parameters)
            
            with open('latitude.conf', 'wb') as configfile:
                config.write(configfile)
                
            # reload accounts
            self.get_accounts()
                
            d = defer.Deferred()
            d.callback('OK')
            return d      
        
class Latitude():
    AUTH_URI = 'https://www.google.com/accounts/ClientLogin'
    BRIDGE_API = 'https://ha-latitude.appspot.com'
    APP_NAME = 'ha-latitude'
    
    def __init__(self, wrapper):
        self.wrapper = wrapper
        self.update_tasks = []
        
        self.start_update_tasks()
        
    def start_update_tasks(self):
        for acc in self.wrapper.accounts:
            l = task.LoopingCall(self.update, acc)
            l.start(float(acc.refreshtime))
            self.update_tasks.append(l)
        
    def restart_update_tasks(self):
        for t in self.update_tasks:
            t.stop()
        
        self.start_update_tasks()
            
    def update(self, account):
        if not account.token:
            self.get_token(account)
        else:
            self.get_latitudedata(account)

    @inlineCallbacks
    def get_token(self, account):
        authreq_data = urllib.urlencode({ "Email":   account.username,
                                          "Passwd":  account.password,
                                          "service": "ah",
                                          "source":  self.APP_NAME,
                                          "accountType": "HOSTED_OR_GOOGLE" })

        response = yield getPage(self.AUTH_URI, method='POST', 
                    postdata=authreq_data, 
                    headers={'Content-Type': 'application/x-www-form-urlencoded'})
        
        auth_resp_dict = dict(x.split("=")
                      for x in response.split("\n") if x)
        account.token = auth_resp_dict["Auth"]
        print "Received token:", account.token
        self.get_latitudedata(account)
        
    @inlineCallbacks
    def get_latitudedata(self, account):               
        serv_args = {}
        serv_args['continue'] = self.BRIDGE_API
        serv_args['auth']     = account.token
        response = yield getPage('%s/_ah/login?%s' % (self.BRIDGE_API, urllib.urlencode(serv_args)))

        try:
            response = json.loads(response)
            account.latitude = response['data']['latitude']
            account.longitude = response['data']['longitude']
            account.lastupdate = datetime.datetime.fromtimestamp(int(response['data']['timestampMs']) //1000)
        except:
            pass
       
        if account.latitude and account.longitude:
            for location, data in self.wrapper.locations.iteritems():
                loc1 = account.latitude, account.longitude
                loc2 = float(data[0]), float(data[1])
                print 'loc1=', loc1
                print 'loc2=', loc2
                print "distance=", self.get_distance_by_haversine(loc1, loc2)
                if self.get_distance_by_haversine(loc1, loc2) < account.proximity:
                    location = location
                    break
                
            if not location:
                location = self.reverse_geocode(account)
            
            values = {'Current location': location}
            self.wrapper.pluginapi.value_update(account.username, values)
    
    @inlineCallbacks
    def reverse_geocode(self, account):
        geocode_url = 'http://maps.google.com/maps/geo?q=%s,%s6&output=json' % (account.latitude, account.longitude)
        response = yield getPage(geocode_url)
        response = json.loads(response)
        location = response['Placemark'][0]['address']
        
        print response        
        print location
        
    def get_distance_by_haversine(self, loc1, loc2):
        '''
        Get distance in km between two locations. 
        Using a haversine formula.
        
        This function is derived from the gislib as used in geolocator:
        http://code.google.com/p/geolocator/source/browse/trunk/geolocator/gislib.py
        
        @param loc1: list of location A given by latitude, longitude
        @param loc2: list of location B given by latitude, longitude
        @return: distance between loc1 and loc2 in KM
        '''
        lat1, lon1 = loc1
        lat2, lon2 = loc2
        
        # convert to radians
        lon1 = lon1 * pi / 180.0
        lon2 = lon2 * pi / 180.0
        lat1 = lat1 * pi / 180.0
        lat2 = lat2 * pi / 180.0
        
        # haversine formula
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = (sin(dlat/2))**2 + cos(lat1) * cos(lat2) * (sin(dlon/2.0))**2
        c = 2.0 * atan2(sqrt(a), sqrt(1.0-a))
        km = 6371.0 * c
        return km

    def is_within_distance(self, loc1, loc2, distance):
        if self.get_distance_by_haversine(loc1, loc2) <= distance: return True
        else: return False
    
class LatitudeAccount():
    def __init__(self, username, password, device_id):
        self.username = username
        self.password = password
        self.token = None
        self.latitude = None
        self.longitude = None
        self.lastupdate = None
        self.refreshtime = None
        self.proximity = None
        self.device_id = device_id
        
    def __str__(self):
        return 'Account: {0}, Latitude: {1}, Longitude: {2}, Last update: {3}'.format(self.username,
                                                                                      self.latitude,
                                                                                      self.longitude,
                                                                                      self.lastupdate)

if __name__ == '__main__':
    wrapper = LatitudeWrapper()
    reactor.run()