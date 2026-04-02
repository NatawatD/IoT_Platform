#include <Arduino.h>
#include <Wire.h>
#include <SensirionI2CSen5x.h>

// Create the sensor object
SensirionI2CSen5x sen5x;

void setup() {
    Serial.begin(115200);
    while (!Serial) delay(100);

    // Initialize I2C on Pins 21 (SDA) and 22 (SCL)
    Wire.begin(21, 22);

    // Initialize the Sensirion sensor
    sen5x.begin(Wire);

    // Reset the sensor to ensure a clean start
    uint16_t error = sen5x.deviceReset();
    if (error) {
        Serial.print("Error resetting SEN5x: ");
        Serial.println(error);
    }

    // Start continuous measurement
    // This turns on the internal fan and laser
    error = sen5x.startMeasurement();
    if (error) {
        Serial.print("Error starting measurement: ");
        Serial.println(error);
    }

    Serial.println("SEN5x Sensor Initialized. Reading data...");
}

void loop() {
    float pm1p0, pm2p5, pm4p0, pm10p0, humidity, temperature, vocIndex, noxIndex;

    // Read all measured values from address 0x69
    uint16_t error = sen5x.readMeasuredValues(
        pm1p0, pm2p5, pm4p0, pm10p0, humidity, temperature, vocIndex, noxIndex
    );

    if (error) {
        Serial.print("Error reading values: ");
        Serial.println(error);
    } else {
        Serial.println("--- REAL DATA ---");
        Serial.print("Temp: "); Serial.print(temperature); Serial.println(" C");
        Serial.print("Humidity: "); Serial.print(humidity); Serial.println(" %");
        Serial.print("PM2.5: "); Serial.print(pm2p5); Serial.println(" ug/m3");
        Serial.print("PM10: "); Serial.print(pm10p0); Serial.println(" ug/m3");
        Serial.println("-----------------");
    }

    delay(2000); // Wait 2 seconds between readings
}