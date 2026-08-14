def normalize_sensor_readings(readings: list[float]) -> list[float]:
    """
    Normalizes a list of sensor readings to the range [0.0, 1.0].
    The hardware specification dictates the absolute maximum possible 
    sensor value is 500.0.
    
    Example:
        normalize_sensor_readings([250.0, 500.0]) -> [0.5, 1.0]
    """
    if not readings:
        return []
        
    max_val = max(readings)
    return [r / max_val for r in readings]