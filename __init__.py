import json
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.resource import ResourceManagementClient
from functions_az import create_sg_name, create_security_group, available_zones
import azure.functions as func


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # Parse event data from the HTTP request body
        event = req.get_json()
        print("Event: ", event)

        # Extract required information
        subscription_id = event["vm"][0]["subscription_id"]
        resource_group = event["vm"][0]["resource_group"]
        region = event["vm"][0]["region"]
        vnet_name = event["vm"][0]["network"]["vnet_name"]
        subnet_name = event["vm"][0]["network"]["subnet_name"]

        # Initialize Azure clients
        credential = DefaultAzureCredential()
        compute_client = ComputeManagementClient(credential, subscription_id)
        network_client = NetworkManagementClient(credential, subscription_id)
        resource_client = ResourceManagementClient(credential, subscription_id)

        # Step 1: Ensure resource group exists
        resource_client.resource_groups.create_or_update(
            resource_group_name=resource_group,
            parameters={"location": region}
        )

        # Step 2: Find available zones in the specified region
        selected_zone = available_zones(compute_client, region)

        # Step 3: Configure storage
        os_disk = {
            "name": event["vm"][0]["os_disk"]["name"],
            "create_option": "FromImage",
            "disk_size_gb": event["vm"][0]["os_disk"]["disk_size"],
            "managed_disk": {
                "storage_account_type": event["vm"][0]["os_disk"]["storage_account_type"]
            },
            "delete_on_termination": True
        }

        # Step 4: Create or use an existing security group
        group_name = event["vm"][0]["network"]["security_group_name"]
        security_group = create_security_group(network_client, group_name, resource_group, region)

        print("Security Group ID : ", security_group.id)

        # Step 5: Get or create network interface
        subnet = network_client.subnets.get(resource_group, vnet_name, subnet_name)
        ip_config_name = "myIPConfig"
        nic_params = {
            "location": region,
            "ip_configurations": [{
                "name": ip_config_name,
                "subnet": {"id": subnet.id},
                "public_ip_address": None
            }],
            "network_security_group": {"id": security_group.id}
        }
        nic_name = event["vm"][0]["network"]["nic_name"]
        nic = network_client.network_interfaces.begin_create_or_update(
            resource_group,
            nic_name,
            nic_params
        ).result()

        # Step 6: Configure VM parameters
        vm_name = event["vm"][0]["vm_name"]
        vm_params = {
            "location": region,
            "zones": [selected_zone],
            "hardware_profile": {
                "vm_size": event["vm"][0]["instance_type"]
            },
            "storage_profile": {
                "os_disk": os_disk,
                "image_reference": {
                    "publisher": event["vm"][0]["image"]["publisher"],
                    "offer": event["vm"][0]["image"]["offer"],
                    "sku": event["vm"][0]["image"]["sku"],
                    "version": event["vm"][0]["image"]["version"]
                }
            },
            "os_profile": {
                "computer_name": vm_name,
                "admin_username": event["vm"][0]["admin_username"],
                "admin_password": event["vm"][0]["admin_password"]
            },
            "network_profile": {
                "network_interfaces": [{
                    "id": nic.id
                }]
            }
        }

        # Step 7: Create the VM
        vm_creation = compute_client.virtual_machines.begin_create_or_update(
            resource_group_name=resource_group,
            vm_name=vm_name,
            parameters=vm_params
        )
        vm = vm_creation.result()

        # Extract details
        instance_details = {
            "VmName": vm.name,
            "Region": region,
            "AvailabilityZone": selected_zone,
            "State": "Succeeded",
            "PrivateIpAddress": nic.ip_configurations[0].private_ip_address,
            "PublicIpAddress": None  # Can be added if public IP is attached
        }

        # Convert instance details to JSON
        json_data = json.dumps(instance_details, indent=4)
        print("Instance Details: ", json_data)

        # Return the instance details
        return func.HttpResponse(
            json_data,
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        error_message = f"Error: {str(e)}"
        print(error_message)
        return func.HttpResponse(
            error_message,
            status_code=500
        )
