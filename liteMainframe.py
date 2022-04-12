
################
#Server application for andrew's lighting mainframe

#Author: Andrew Cisneros

#About:

#Peripherals are placed at doorways/entrances thoughout the living space
#When the resident passes through a doorway - peripherals set a byte characterisitc corresponding to an entry or exit

#This application recieves the changes characteristic value via BLE indications
#The app then activates the neccessary lights 


################

#Packages for dbus bluetooh low energy
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

from govee_api_laggat import Govee
from phue import Bridge

import threading
import asyncio
import dbus
import time
import logging as log
import os

#Bluez dbus service
BLUEZ_SERVICE_NAME = "org.bluez"
#Interfaces for communication with dbus proxy objects
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
PROPERTIES_IFACE =  "org.freedesktop.DBus.Properties"
ADAPTER_IFACE = "org.bluez.Adapter1"
DEVICES_IFACE = "org.bluez.Device1"
AGENT_IFACE = "org.bluez.AgentManager1"
SERVICE_IFACE = "org.bluez.GattService1"
CHARACTERISTIC_IFACE = "org.bluez.GattCharacteristic1"

bluezInterface = None

#Value of data flag from ble devices
ENTER_ROOM = 0x02
EXIT_ROOM = 0x01

#Index of light type in tuple events
GOVEE_INDEX = 0
HUE_INDEX = 1

#BT address of bedroom beacon
BEDROOM_MAC = "4C:EB:D6:4C:B3:7A"
CHARACTERISTIC_UUID = "19b10012-e8f2-537e-4f6c-d104768a1214"

#Govee api key - used for making connection to govee cloud
govee_api_key = "b7da95be-8594-4041-a9b6-a10206d416c3"

#Discovery status
discoveryStatus = False
#Program status variable
running = True 

#Task function passed to threading.Thread
#threading will not accept asyncio funcs - this is the work around
def between_task_govee():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    coroutine = task_govee()
    loop.run_until_complete(coroutine)

# Task runs for the duration of the program
#
# Function is responsible for turning on and off govee enabled lights
async def task_govee():
    global running
    global bedroom_light_on
    global bedroom_light_off

    log.info("task_govee started!")
    
    #Object for govee bedroom lamp
    bedroom_lamp = None

    #Connect to govee cloud with api key
    #Key obtained though govee mobile app
    async with Govee(govee_api_key) as govee:
        devices, err = await govee.get_devices()
        #Find with specific name
        #Devices named in the mobile app
        for dev in devices:
            devAddress, devObj  = govee._get_device(dev)
            if (devObj.device_name == "Lamp"):
                log.info("Connected to govee bedroom lamp")
                bedroom_lamp = dev

        #Run for duration of program
        #Responsible for turning on/off govee lamp
        while(running):
            if (bedroom_light_on[GOVEE_INDEX]):
                log.info("Turing on govee bedroom lamp")
                #configure device to set brightness to 100% before turning on 
                bedroom_lamp.before_set_brightness_turn_on = True
                success, err = await govee.set_brightness(bedroom_lamp, 254)
                success, err = await govee.turn_on(bedroom_lamp)
                bedroom_light_on[GOVEE_INDEX] = False
            if (bedroom_light_off[GOVEE_INDEX]):
                log.info("Turning off govee bedroom lamp")
                await govee.turn_off(bedroom_lamp)
                bedroom_light_off[GOVEE_INDEX] = False
                
            await asyncio.sleep(0.01)
        log.info("task_govee finished!")


#Thread shall be responsible for controllng phillips hue smart lights
#
#When a sensor peripheral detects a body enters/exits an entryway, a characteristic is changed corresponding to entering/exiting
#The BLE thread monitors this characteristic and sets an event to turn on/off the appropriate light
def task_hue():
    global running
    global bedroom_light_on
    global bedroom_light_off
    
    log.info("task hue started!")
    
    b = Bridge('192.168.1.64')
    b.connect()
    
    log.info("Connected to hue bridge")
    
    hueLights = b.get_light_objects('name')
    
    while(running):
        
        if (bedroom_light_on[HUE_INDEX]):
            log.info("turning on hue bedroom lamp")
            hueLights['Bedside lamp'].on = True
            hueLights['Bedside lamp'].brightness = 254
            bedroom_light_on[HUE_INDEX] = False
            
        if (bedroom_light_off[HUE_INDEX]):
            hueLights['Bedside lamp'].on = False
            bedroom_light_off[HUE_INDEX] = False
    
        time.sleep(0.01)
    log.info('task_hue finished!')
    
      
# Handle any change in a BLE devices properties
#
# Properties include: RSSI and manufacturer data
#
# When manufacturer data indicates a resident passed through a doorway
# Set appropriate flag for govee/hue task to active the corresponding light
def on_dev_properties_changed(interface_name, changed_properties, invalidated_properties):
    global bedroom_light_on
    global bedroom_light_off
    #Get data of interest
    rssi = changed_properties.get('RSSI')
    connStatus = changed_properties.get('Connected')

    #Display mac address with rssi
    if rssi:
        log.info("Bedroom Peripheral: RSSI: %d\n", rssi)

    #Log connection sucess
    if connStatus is not None:
        log.info("Bedroom Peripheral connection status changed: %d", connStatus)
   

def on_char_properties_changed(interface_name, changed_properties, invalidated_properties):    
    val = changed_properties["Value"][0]    
    
    if (val):
        if (val == ENTER_ROOM):
            log.info("Body detected!: Entering Room")
            bedroom_light_on[GOVEE_INDEX] = True
            bedroom_light_on[HUE_INDEX] = True
        elif (val == EXIT_ROOM):
            log.info("Body detected!: Exiting Room")
            bedroom_light_off[GOVEE_INDEX] = True
            bedroom_light_off[HUE_INDEX] = True

#Handle the characteristic
def on_characteristic_found(path):
    characteristicIface = dbus.Interface(dbussys.get_object(BLUEZ_SERVICE_NAME, path), CHARACTERISTIC_IFACE)
    propsIface = dbus.Interface(dbussys.get_object(BLUEZ_SERVICE_NAME, path), PROPERTIES_IFACE)
    log.info("Established interface with bedroom entry characterisitic")
    
    #Start notifiaction session from this characteristic
    characteristicIface.StartNotify()
    #Characteristics changed by the peripherals wil be upated through the peroperties changed signal. connect to signal
    propsIface.connect_to_signal('PropertiesChanged', on_char_properties_changed)
        
        
# Function handles the discovery of new devices via BlueZ
# If the device has a mac address we are interesting in, connect to the device's interface
# and subcribe to a signal for any change in device properties
def on_device_found(device_path, device_props):
    address = device_props.get('Address')

    if(address == BEDROOM_MAC):
        #wait until we're done scanning until we connect
        #Bluez won't allow us to stop scanning after we've established a connection (idk why)
        while (discoveryStatus == True):
            time.sleep(0.2)
        
        #object export path: '/org/bluez/hci0/dev_4C_EB_D6_4C_B3_7A'
        devProxy = dbussys.get_object(BLUEZ_SERVICE_NAME, device_path)
        
        #get device interafce and establish connection
        devIface = dbus.Interface(devProxy, DEVICES_IFACE)
        devIface.Connect()
        
        devPropsIface = dbus.Interface(devProxy, PROPERTIES_IFACE)
        
        #Wait for connection
        connStatus = None
        while (connStatus != True):
            connStatus = devPropsIface.Get(DEVICES_IFACE, 'Connected')
            log.info("Connection status to %s: %d", BEDROOM_MAC, connStatus)
            time.sleep(0.5)
        #Allow time for object manager to retrive new services, characeristics and descriptor objects
        time.sleep(2)
                    
        #asssigning signal handler to track RSSI and connection disconnects
        devPropsIface.connect_to_signal('PropertiesChanged', on_dev_properties_changed)
        
        #Find the characterisitcs of interest
        objects = bluezInterface.GetManagedObjects()
        for path in objects:
            charUuid = objects[path].get(CHARACTERISTIC_IFACE, {}).get('UUID')
            if (charUuid == CHARACTERISTIC_UUID):
                on_characteristic_found(path)
                
    
#Function handles any new interfaces created by bluez dbus service
#
#If a device interface is found - run on_device_found routine
def on_iface_added(path, interfaces_and_properties):
    ifaces = interfaces_and_properties.keys()

    if DEVICES_IFACE in ifaces:
        on_device_found(path, interfaces_and_properties[DEVICES_IFACE])

        
##### -----  MAIN  ----- #####

if __name__ == '__main__':

    os.system("cat /dev/null > /home/pi/liteMainframe/liteMainframe.log")
    log.basicConfig(filename='/home/pi/liteMainframe/liteMainframe.log', encoding='utf-8', format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p', level=log.INFO)
    
    log.info("Lite Mainframe Started!")
    
    #EVENTS
    #Bedroom light events
    bedroom_light_on = [False, False]
    bedroom_light_off = [False, False]

    #For bluez asyncronous operation
    DBusGMainLoop(set_as_default=True)

    #Connect to dbus system bus
    dbussys = dbus.SystemBus()

    #Get dbus proxy objects
    dbusconnection = dbussys.get_object(BLUEZ_SERVICE_NAME, "/")
    bluezProxy = dbussys.get_object(BLUEZ_SERVICE_NAME, "/org/bluez")
    hciProxy = dbussys.get_object(BLUEZ_SERVICE_NAME, '/org/bluez/hci0')

    #Create dbus interfaces
    bluezInterface = dbus.Interface(dbusconnection, DBUS_OM_IFACE)
    adapterInterface = dbus.Interface(hciProxy, ADAPTER_IFACE)
    propsInterface = dbus.Interface(hciProxy, PROPERTIES_IFACE)
    agentInterface = dbus.Interface(bluezProxy, AGENT_IFACE)

    #Start Govee Task - handles turning on/off govee lights
    goveeThread = threading.Thread(target = between_task_govee)
    goveeThread.start()

    #Start Hue task - handle turning on/off phillips hue lights
    hueThread = threading.Thread(target = task_hue)
    hueThread.start()

    #Setup bluez signal for handleing new interfaces
    bluezInterface.connect_to_signal('InterfacesAdded', on_iface_added)

    #Power cycle the bluetooth module
    propsInterface.Set(ADAPTER_IFACE, 'Powered', dbus.Boolean(0))
    time.sleep(2)
    propsInterface.Set(ADAPTER_IFACE, 'Powered', dbus.Boolean(1))
    
    #Remove any bt addresses of interest from bluez cached devices
    objects = bluezInterface.GetManagedObjects()
    for path in objects:
        address = objects[path].get(DEVICES_IFACE, {}).get('Address')

        if (address == BEDROOM_MAC):
            try:
                adapterInterface.RemoveDevice(path)
                log.info("Success to remove pre-existing device!")
            except:
                log.info("Could not remove pre-existing device")
    
    #Configure agent
    try:
        agentInterface.UnregisterAgent("/org/bluez")
    except:
        log.info("Could not remove pre-existing agent")
        
    time.sleep(1)
    agentInterface.RegisterAgent("/org/bluez", "NoInputNoOutput")
    
    #Start scaning primary ble channels
    adapterInterface.SetDiscoveryFilter({'DuplicateData': dbus.Boolean(0)}) 
    discoveryStatus = True
    adapterInterface.StartDiscovery()
    log.info("Starting ble discovery!")
    time.sleep(5)
    log.info("Stopping ble discovery!")
    discoveryStatus = False
    adapterInterface.StopDiscovery()
   
    try:
        GLib.MainLoop().run()
    except KeyboardInterrupt:
        log.info("Ctrl-c caught!")
        #Stop govee task
        running = False
        goveeThread.join()
        hueThread.join()
        adapterInterface.StopDiscovery()
        propsInterface.Set(ADAPTER_IFACE, 'Powered', dbus.Boolean(0))
        log.info("Bluetooth module off.")
        GLib.MainLoop().quit()
        log.info("Program exiting!")
