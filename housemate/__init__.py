import json
import traceback
from abc import abstractmethod

import stomp


def serialise(obj):

    def to_camel_case(value):
        def camelcase():
            yield str.lower
            while True:
                yield str.capitalize

        c = camelcase()
        return "".join(c.next()(x) if x else "_" for x in value.split("_"))

    """ JSON serializer for objects not serializable by default json code"""

    """ Do something different for special objects """
    # if isinstance(obj, date):
    #    serial = obj.isoformat()
    #    return serial

    """ for an object, return its dict, but first convert all keys to the camelCase """
    result = {}
    for key in obj.__dict__:
        result[to_camel_case(key)] = obj.__dict__[key]
    return result


# Implementation of stomp message listener that maintains a map of destination -> callback and calls that callback with
# the deserialised object
class MessageListener(stomp.ConnectionListener):

    def __init__(self):
        self.callbacks = {}

    def subscribe(self, path, callback, dict_to_obj):
        self.callbacks[path] = (callback, dict_to_obj)

    def on_error(self, headers, message):
        print('received an error "%s"' % message)

    def on_message(self, headers, message):
        # Find the destination
        if 'destination' in headers:
            if headers['destination'] in self.callbacks:
                # Call the callback for the destination
                try:
                    print 'Received "%s" on "%s' % (message, headers['destination'])
                    (callback, dict_to_obj) = self.callbacks[headers['destination']]
                    callback(dict_to_obj(json.loads(message)))
                except Exception:
                    print 'Failed to process message:'
                    traceback.print_exc()
            else:
                print 'received a message for "%s" but no listener registered' % headers['destination']
        else:
            print 'received a message with no destination'


# Wrapper around a stomp connection with HM specific ways of sending messages and listening to a topic
class HMConnection:

    def __init__(self, host, port):
        self.conn = stomp.Connection(host_and_ports=[(host, port)])
        self.message_listener = MessageListener()
        self.conn.set_listener('', self.message_listener)
        self.conn.start()
        self.conn.connect(wait=True)

    def send(self, path, data, persist=True):
        json_string = json.dumps(data, default=serialise)
        print 'Sending "%s" on "%s' % (json_string, path)
        self.conn.send(body=json_string, destination=path, headers={'com.intuso.housemate.message.store': persist})

    def register(self, path, callback, dict_to_json):
        self.conn.subscribe(path, path)
        self.message_listener.subscribe(path, callback, dict_to_json)

    def disconnect(self):
        self.conn.disconnect()


# HM data class and subclasses where they contain extra data. Contains _type so can be deserialised to correct type,
# object_class (basically same as type but a property of the resulting deserialised object), id, name and description
class Data:

    def __init__(self, subtype, object_class, object_id, name, description):
        self._type = subtype
        self.object_class = object_class
        self.id = object_id
        self.name = name
        self.description = description


class DeviceConnectedData(Data):

    def __init__(self, subtype, object_class, object_id, name, description, abilities, classes):
        Data.__init__(self, subtype, object_class, object_id, name, description)
        self.abilities = abilities
        self.classes = classes


# HM value. Has a string value and/or a map of child values
class TypeInstance:

    def __init__(self, value, children=None):
        # Check what value is and make sure it's a string
        if isinstance(value, basestring):
            self.value = value
        else:
            self.value = str(value)
        # Check what childValues is and make sure it's a TypeInstanceMap
        self.children = {} if children is None else children


# HM objects for performing commands and sending status back
class Perform:

    def __init__(self, op_id, instance_map):
        self.op_id = op_id
        # Make sure instanceMap is a TypeInstancesMap
        self.instanceMap = instance_map


class PerformStatus:

    def __init__(self, op_id, finished=False, error=None):
        self.op_id = op_id
        self.finished = finished
        self.error = error

    def perform_finished(self, error=None):
        self.finished = True
        self.error = error


# Types
class Type:

    def __init__(self):
        pass

    @abstractmethod
    def to_value(self, instances):
        raise NotImplementedError()

    @abstractmethod
    def from_value(self, value):
        raise NotImplementedError()


class PrimitiveType(Type):

    def __init__(self, parse):
        Type.__init__(self)
        self.parse = parse

    def to_value(self, instances):
        return self.parse(instances[0]['value']) if isinstance(instances, list) and len(instances) > 0 else None

    def from_value(self, value):
        return [{"value": str(value)}]  # temp fix while HM UI is case sensitive


class BooleanType(PrimitiveType):

    def __init__(self):
        PrimitiveType.__init__(self, bool)


class FloatType(PrimitiveType):

    def __init__(self):
        PrimitiveType.__init__(self, float)


class IntegerType(PrimitiveType):

    def __init__(self):
        PrimitiveType.__init__(self, int)


class LongType(PrimitiveType):

    def __init__(self):
        PrimitiveType.__init__(self, long)


class StringType(PrimitiveType):

    def __init__(self):
        PrimitiveType.__init__(self, str)


# Methods to create objects from json parsed into a dict
def dict_to_perform(json_dict):
    return None if json_dict is None else Perform(json_dict['opId'], json_dict['instanceMap'])
