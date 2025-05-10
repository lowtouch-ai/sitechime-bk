"""
Utility functions for converting between JSON and YAML formats.
"""
import json
import yaml


def json_to_yaml(json_data):
    """
    Convert JSON data to YAML format.
    
    Args:
        json_data (str or dict): JSON data as a string or dictionary
        
    Returns:
        str: YAML formatted string
    """
    # If input is a string, parse it as JSON
    if isinstance(json_data, str):
        try:
            data = json.loads(json_data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON data: {e}")
    else:
        data = json_data
    
    # Convert to YAML
    try:
        yaml_data = yaml.dump(data, default_flow_style=False, sort_keys=False)
        return yaml_data
    except Exception as e:
        raise ValueError(f"Error converting to YAML: {e}")


def yaml_to_json(yaml_data):
    """
    Convert YAML data to JSON format.
    
    Args:
        yaml_data (str): YAML data as a string
        
    Returns:
        str: JSON formatted string
    """
    # Parse YAML
    try:
        data = yaml.safe_load(yaml_data)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML data: {e}")
    
    # Convert to JSON
    try:
        json_data = json.dumps(data, indent=2)
        return json_data
    except Exception as e:
        raise ValueError(f"Error converting to JSON: {e}")
