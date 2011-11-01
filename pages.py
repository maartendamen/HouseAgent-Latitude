from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
import json
from mako.lookup import TemplateLookup
from mako.template import Template
from twisted.web.static import File
import os
from twisted.internet.defer import inlineCallbacks

def init_pages(web, coordinator, db):
    web.putChild('latitude_accounts', Latitude_accounts())
    web.putChild('latitude_account', Latitude_account(coordinator, db))
    web.putChild('latitude_accounts_data', Latitude_accounts_data(coordinator, db))
    web.putChild('latitude_locations_data', Latitude_locations_data(coordinator, db))
    web.putChild('latitude_locations', Latitude_locations())
    web.putChild('latitude_location', Latitude_location(coordinator))
    web.putChild("latitude_images", File(os.path.join('houseagent/plugins/latitude/templates/images')))
    
class Latitude_accounts(Resource):
    def render_GET(self, request):
        lookup = TemplateLookup(directories=['houseagent/templates/'])
        template = Template(filename='houseagent/plugins/latitude/templates/accounts.html', lookup=lookup)
        
        return str(template.render())  
    
class Latitude_account(Resource):
    
    def __init__(self, coordinator, db):
        self.coordinator = coordinator
        self.db = db
        
    def result(self, result):
        self.request.write("OK")
        self.request.finish()

    @inlineCallbacks
    def device_saved(self, result, name, password, refreshtime, proximity):
        device_id = yield self.db.query_latest_device_id()
        data = {'name': name, 'details': [device_id[0][0], password, refreshtime, proximity]}
        self.coordinator.send_custom(self.pluginguid, 'add_account', data).addCallback(self.result)

    def render_POST(self, request):
        self.request = request
        operation = request.args['oper'][0]
                
        plugins = self.coordinator.get_plugins_by_type("Latitude")
        if len(plugins) == 0:
            self.request.write(str("No online latitude plugins found..."))
            self.request.finish()
        elif len(plugins) == 1:
            self.pluginguid = plugins[0].guid    
            pluginid = plugins[0].id
            locationid = plugins[0].location_id            
        
        if operation == 'add':
            name = request.args['name'][0]
            device_name = request.args['device_name'][0]
            password = request.args['password'][0]
            proximity = request.args['proximity'][0]
            refreshtime = request.args['refreshtime'][0]
            
            self.db.save_device(device_name, name, pluginid, locationid).addCallback(self.device_saved, name, password, refreshtime, proximity)
            return NOT_DONE_YET
        
        elif operation == 'del':
            name = request.args['id'][0]
            self.coordinator.send_custom(self.pluginguid, 'del_account', name).addCallback(self.result) 
                
        return NOT_DONE_YET
    
class Latitude_accounts_data(Resource):
    def __init__(self, coordinator, db):
        self.coordinator = coordinator
        self.db = db
    
    @inlineCallbacks
    def result(self, result):
        output = []
        for account, data in result.iteritems():
            device_name = yield self.db.query_device(data[0])
            
            acc = {'name': account,
                   'device_name': device_name[0][1],
                   'id': data[0],
                   'password': data[1],
                   'refreshtime': data[2],
                   'proximity': data[3],
                   'latitude': data[4],
                   'longitude': data[5],
                   'updatetime': data[6]}
            output.append(acc)
            
        self.request.write(json.dumps(output))
        self.request.finish()
    
    def render_GET(self, request):
        self.request = request
        plugins = self.coordinator.get_plugins_by_type("Latitude")
        
        if len(plugins) == 0:
            self.request.write(str("No online latitude plugins found..."))
            self.request.finish()
        elif len(plugins) == 1:
            self.pluginguid = plugins[0].guid
            self.pluginid = plugins[0].id
            self.coordinator.send_custom(plugins[0].guid, "get_accounts", '').addCallback(self.result)   
                
        return NOT_DONE_YET
    
class Latitude_location(Resource):
    
    def __init__(self, coordinator):
        self.coordinator = coordinator
        
    def result(self, result):
        self.request.write("OK")
        self.request.finish()

    def render_POST(self, request):
        self.request = request
        pluginguid = None
        operation = request.args['oper'][0]
                
        plugins = self.coordinator.get_plugins_by_type("Latitude")
        if len(plugins) == 0:
            self.request.write(str("No online latitude plugins found..."))
            self.request.finish()
        elif len(plugins) == 1:
            pluginguid = plugins[0].guid    
        
        if operation == 'add':
            latitude = request.args['latitude'][0]
            longitude = request.args['longitude'][0]
            location = request.args['location'][0]
            
            data = {'name': location, 'coordinates': [latitude, longitude]}
            self.coordinator.send_custom(pluginguid, 'add_location', data).addCallback(self.result)
        elif operation == 'del':
            name = request.args['id'][0]
            self.coordinator.send_custom(pluginguid, 'del_location', name).addCallback(self.result)
        elif operation == 'edit':
            latitude = request.args['latitude'][0]
            longitude = request.args['longitude'][0]
            location = request.args['location'][0]
            id = request.args['id'][0]
            
            data = {'name': location, 'coordinates': [latitude, longitude], 'id': id}
            self.coordinator.send_custom(pluginguid, 'edit_location', data).addCallback(self.result)
                
        return NOT_DONE_YET

class Latitude_locations(Resource):
    def render_GET(self, request):
        lookup = TemplateLookup(directories=['houseagent/templates/'])
        template = Template(filename='houseagent/plugins/latitude/templates/locations.html', lookup=lookup)
        
        return str(template.render())
    
class Latitude_locations_data(Resource):
    def __init__(self, coordinator, db):
        self.coordinator = coordinator
        
    def result(self, result):
        output = []
        for location, data in result.iteritems():
            loc = {'location': location,
                   'latitude': data[0],
                   'longitude': data[1]}
            output.append(loc)
            
        self.request.write(json.dumps(output))
        self.request.finish()
    
    def render_GET(self, request):
        self.request = request
        plugins = self.coordinator.get_plugins_by_type("Latitude")
        
        if len(plugins) == 0:
            self.request.write(str("No online latitude plugins found..."))
            self.request.finish()
        elif len(plugins) == 1:
            self.pluginguid = plugins[0].guid
            self.pluginid = plugins[0].id
            self.coordinator.send_custom(plugins[0].guid, "get_locations", '').addCallback(self.result)   
                
        return NOT_DONE_YET