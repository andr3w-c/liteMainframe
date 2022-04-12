#include <ArduinoBLE.h>

#define OUTSIDE_PROX 2
#define INSIDE_PROX 3

#define INSIDE_FLAG 0x01
#define OUTSIDE_FLAG 0x02

BLEService liteService("19B10010-E8F2-537E-4F6C-D104768A1214"); // create service
// create sensor characteristic and allow remote device to get notifications
BLEByteCharacteristic sensorCharacteristic("19B10012-E8F2-537E-4F6C-D104768A1214", BLERead | BLEIndicate);

enum state {
  WAITING,
  PENDING,
  ALERT,
  NUM_STATES
};

struct timer {
  unsigned long startTime;
  unsigned long currentTime;
  unsigned long expireTime;
  bool active;  
};

byte data = 0x00;

//Construct timer used for staying in alert mode
timer alertTimer = {
  0,
  0,
  4000,
  false
 };

timer pendingTimer = {
  0,
  0,
  2500,
  false
};

volatile state nextState = WAITING;
state currentState = WAITING;

void blePeripheralConnectHandler(BLEDevice central) {
  // central connected event handler
  Serial.print("Connected event, central: ");
  Serial.println(central.address());
}

void blePeripheralDisconnectHandler(BLEDevice central) {
  // central disconnected event handler
  Serial.print("Disconnected event, central: ");
  Serial.println(central.address());
}

void insideSensor() {

  Serial.println("INSIDE MOTION");

  if (currentState == WAITING)
  {
    data= INSIDE_FLAG;
    nextState = PENDING;
  }
  else if (currentState == PENDING)
  {
    stopTimer(pendingTimer);
    nextState = ALERT;
  }
}

void outsideSensor() {
   Serial.println("OUTSIDE MOTION");

   if (currentState == WAITING)
   {
    data = OUTSIDE_FLAG;
    nextState = PENDING;
   }
   else if (currentState == PENDING)
   {
    stopTimer(pendingTimer);
    nextState = ALERT;
   }
}

void startTimer(timer &myTimer)
{
  myTimer.startTime = millis();
  myTimer.active = true;
}

void stopTimer(timer &myTimer)
{
  myTimer.active = false;
}

void updateTimer(timer &myTimer)
{
  myTimer.currentTime = millis();
}

bool isTimerExpired(timer &myTimer)
{
  bool retVal = false;
  
  if (myTimer.currentTime - myTimer.startTime >= myTimer.expireTime)
  {
    myTimer.active = false;
    retVal = true;
  }

  return retVal;
}

void setup() {
  // put your setup code here, to run once:

    Serial.begin(9600);
    pinMode(LED_BUILTIN, OUTPUT);
    pinMode(INSIDE_PROX, INPUT);
    pinMode(OUTSIDE_PROX, INPUT);

  if (!BLE.begin()) {
    Serial.println("BLE module failed!");

    //Do not continue
    while (1);
  }

  // assign event handlers for connected, disconnected to peripheral
  BLE.setEventHandler(BLEConnected, blePeripheralConnectHandler);
  BLE.setEventHandler(BLEDisconnected, blePeripheralDisconnectHandler);

  //Set PDU type to ADV_CONN_IND (allow connections)
  BLE.setConnectable(true);
  //Configure GATT server
  liteService.addCharacteristic(sensorCharacteristic);
  BLE.addService(liteService);
  sensorCharacteristic.writeValue(data);

  
  attachInterrupt(digitalPinToInterrupt(OUTSIDE_PROX), outsideSensor, RISING);
  attachInterrupt(digitalPinToInterrupt(INSIDE_PROX), insideSensor, RISING);
  BLE.advertise();

  Serial.print("MAC: ");
  Serial.println(BLE.address());

  currentState = WAITING;
}

void loop() {  

  BLE.poll();
  //HANDLE STATE MACHINE//
  if (currentState != nextState)
  {
    if (nextState == ALERT) 
    { 
      Serial.println("Entered Alert mode");
      sensorCharacteristic.writeValue(data);
      Serial.println("Started alert timer");
      startTimer(alertTimer);
    }
    else if (nextState == WAITING)
    {
      Serial.println("Entered Waiting mode");
      data = 0x00;
      sensorCharacteristic.writeValue(data);
    }
    else if (nextState == PENDING)
    {
      Serial.println("Entered Pending mode");
      startTimer(pendingTimer);
    }
    
    currentState = nextState;
  }

  //=======Handle Timers========//
  if (alertTimer.active)
  {
    updateTimer(alertTimer);
    
    if (isTimerExpired(alertTimer))
    {
      Serial.println("Alert Timer expired!!");
      nextState = WAITING;
    }
  }

  if (pendingTimer.active)
  {
    updateTimer(pendingTimer);

    if (isTimerExpired(pendingTimer))
    {
      Serial.println("Pending Timer expired!");
      nextState = WAITING;
    }
  }
  //=============================//
}
