from abc import abstractmethod
from housemate import Data, PerformStatus, dict_to_perform, DeviceConnectedData, IntegerType, BooleanType, FloatType


# Real objects
class RealObject:

    def __init__(self, conn, path, data):
        self.conn = conn
        self.path = path
        self.data = data
        self.publish_data()

    def publish_data(self):
        self.conn.send(self.path, self.data)


class RealCommand(RealObject):

    def __init__(self, parent,id, name, description, command_callback):
        RealObject.__init__(self, parent.conn, parent.path + '.' + id,
                            Data('command', 'command', id, name, description))
        self.parameters = RealList(self, 'parameters', 'Parameters', 'Parameters')
        self.command_callback = command_callback
        self.conn.register(self.path + '.perform', self.perform, dict_to_perform)

    def perform(self, perform):
        status = PerformStatus(perform.op_id)
        self.conn.send(self.path + '.performStatus', status, persist=False)
        print 'Performing "%s"' % self.path
        self.command_callback(
            *map(lambda parameter: parameter.parameter_type.to_value(perform.instanceMap[parameter.data.id]),
                 self.parameters.elements))
        status.perform_finished()
        self.conn.send(self.path + '.performStatus', status, persist=False)

    def add_parameter(self, id, name, description, parameter_type):
        parameter = RealParameter(self.parameters, id, name, description, parameter_type)
        self.parameters.add(parameter)
        return parameter


class RealDeviceConnected(RealObject):

    def __init__(self, parent,id, name, description, abilities, classes):
        RealObject.__init__(self, parent.conn, parent.path + '.' + id,
                            DeviceConnectedData('deviceConnected', 'device-connected', id, name, description,
                                                [name for ability in abilities for name in ability.names()], classes))
        self.commands = RealList(self, 'commands', 'Commands', 'Commands')
        self.values = RealList(self, 'values', 'Values', 'Values')
        for ability in abilities:
            ability.configure(self)

    def add_command(self, id, name, description, command_callback):
        command = RealCommand(self.commands, id, name, description, command_callback)
        self.commands.add(command)
        return command

    def add_value(self, id, name, description, value_type):
        value = RealValue(self.values, id, name, description, value_type)
        self.values.add(value)
        return value


class RealHardware(RealObject):

    def __init__(self, parent,id, name, description):
        RealObject.__init__(self, parent.conn, parent.path + '.' + id,
                            Data('hardware', 'hardware', id, name, description))
        self.devices = RealList(self, 'devices', 'Devices', 'Devices')

    def add_device_connected(self, id, name, description, abilities, classes):
        device = RealDeviceConnected(self.devices, id, name, description, abilities, classes)
        self.devices.add(device)
        return device


class RealList(RealObject):

    def __init__(self, parent,id, name, description):
        RealObject.__init__(self, parent.conn, parent.path + '.' + id,
                            Data('list', 'list', id, name, description))
        self.elements = []

    def add(self, element):
        self.elements.append(element)


class RealNode(RealObject):

    def __init__(self, conn, id, name, description):
        RealObject.__init__(self, conn, '/topic/real.1-0.json.nodes.' + id,
                            Data('node', 'node', id, name, description))
        self.hardwares = RealList(self, 'hardwares', 'Hardwares', 'Hardwares')

    def add_hardware(self, id, name, description):
        hardware = RealHardware(self.hardwares, id, name, description)
        self.hardwares.add(hardware)
        return hardware


class RealParameter(RealObject):

    def __init__(self, parent,id, name, description, parameter_type):
        RealObject.__init__(self, parent.conn, parent.path + '.' + id,
                            Data('value', 'value', id, name, description))
        self.parameter_type = parameter_type


class RealValue(RealObject):

    def __init__(self, parent,id, name, description, value_type):
        RealObject.__init__(self, parent.conn, parent.path + '.' + id,
                            Data('value', 'value', id, name, description))
        self.value_type = value_type

    def set(self, value):
        self.conn.send(self.path + '.value', self.value_type.from_value(value))


# Abilities
class Ability:

    def __init__(self):
        pass

    @abstractmethod
    def names(self):
        raise NotImplementedError

    @abstractmethod
    def configure(self, device):
        raise NotImplementedError


class Power(Ability):

    def __init__(self, on_callback, off_callback):
        Ability.__init__(self)
        self.on_callback = on_callback
        self.off_callback = off_callback
        self.on_value = None

    def names(self):
        return ['power']

    def set_on(self, on):
        self.on_value.set(on)

    def on(self):
        self.on_callback()
        self.set_on(True)

    def off(self):
        self.off_callback()
        self.set_on(False)

    def configure(self, device):
        device.add_command('on', 'On', 'Turn on', self.on)
        device.add_command('off', 'Off', 'Turn off', self.off)
        self.on_value = device.add_value('on', 'On', 'Whether the device is on', BooleanType())


class PowerVariable(Power):

    def __init__(self, on_callback, off_callback, set_callback, increase_callback, decrease_callback):
        Power.__init__(self, on_callback, off_callback)
        self.set_callback = set_callback
        self.increase_callback = increase_callback
        self.decrease_callback = decrease_callback
        self.percent_value = None

    def names(self):
        return ['power.variable']

    def set_percent(self, percent):
        self.percent_value.set(percent)

    def set(self, percent):
        self.set_callback(percent)
        self.set_percent(percent)

    def increase(self):
        self.set_percent(self.increase_callback())

    def decrease(self):
        self.set_percent(self.decrease_callback())

    def configure(self, device):
        Power.configure(self, device)
        set_command = device.add_command('set', 'Set', 'Set power', self.set)
        set_command.add_parameter('percent', 'Percent', 'Percent', IntegerType())
        device.add_command('increase', 'Increase', 'Increase power', self.increase)
        device.add_command('decrease', 'Decrease', 'Decrease power', self.decrease)
        self.percent_value = device.add_value('percent', 'Percent', 'Percent', IntegerType())


class TemperatureSensor(Ability):

    def __init__(self):
        Ability.__init__(self)
        self.temperature_value = None

    def names(self):
        return ['temperaturesensor']

    def set_temperature(self, temperature):
        self.temperature_value.set(temperature)

    def configure(self, device):
        self.temperature_value = device.add_value('temperature', 'Temperature', 'Temperature', FloatType())


class Thermostat(TemperatureSensor):

    def __init__(self, set_callback):
        TemperatureSensor.__init__(self)
        self.set_callback = set_callback

    def names(self):
        return ['temperaturesensor.thermostat']

    def set(self, temperature):
        self.set_callback(temperature)
        self.set_temperature(temperature)

    def configure(self, device):
        TemperatureSensor.configure(self, device)
        set_command = device.add_command('set', 'Set', 'Set power', self.set)
        set_command.add_parameter('percent', 'Percent', 'Percent', FloatType())
