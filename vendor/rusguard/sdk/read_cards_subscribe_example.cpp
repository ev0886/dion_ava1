#include <cstdint>
#include <cstdio>
#include <vector>

// ReaderSDK
#include <api_types.h>
#include <api_error_codes.h>
#include <dll.h>
#include <string>
#include <cstring>
#include <thread>

const char* device_type_to_device_name(uint8_t deviceType) {
	switch (deviceType) {
		case DTE_R10EHT:			return "R10-EHT";
		case DTE_R10MF:				return "R10-MF";
		case DTE_R15MULTI:			return "R15 Multi";
		case DTE_R5USBMULTI:		return "R5-USB Multi";
		case DTE_R5USBMULTIPROF:	return "R5-USB Multi Prof";
		case DTE_R10MF_BIO:			return "R10-MF BIO";
		case DTE_R10MF_QR:			return "R10-MF QR";
		case DTE_RDR204EH:			return "RDR204-EH Key";
		case DTE_RDR204MF:			return "RDR204-MF Key";
		case DTE_RDR102:			return "RDR-102";
		default:
			return "Unknown";
	}
}

const char* endpoint_type_to_endpoint_name(uint8_t endpointType) {
	switch (endpointType) {
		case E_RG_ENDPOINT_TYPE::ET_SERIAL:
			return "SERIAL";
		case ET_USBHID:
			return "USB HID";
		default:
			return "Unknown";
	}
}

const char* card_type_code_to_card_type_name(uint8_t cardTypeCode) {
	switch (cardTypeCode) {
		case CTC_PIN: return "PIN Code";
		case CTC_TEMIC: return "Temic";
		case CTC_HID: return "HID";
		case CTC_EM: return "Em-Marine";
		case CTC_INDALA: return "Indala";
		case CTC_COTAG: return "COTAG";
		case CTC_MF_DESFIRE: return "Mifare Desfire";
		case CTC_MF_UL: return "Mifare Ultralight";
		case CTC_MF_MINI: return "Mifare mini";
		case CTC_MF_CL1K_PL2K: return "Miface Classic 1K/Plus 2K";
		case CTC_MF_CL4K_PL4K: return "Mifare Classic/Plus 4K";
		case CTC_MF_PL2K_SL2: return "Mifare Plus 2K SL2";
		case CTC_MF_PL4K_SL2: return "Mifare Plus 4K SL2";
		case CTC_MF_SL3: return "Mifare Plus SL3";
		case CTC_SMX4K: return "SmartMX 4K";
		case CTC_SMX1K: return "SmartMX 1K";
		case CTC_CLONE_ON_TEMIC: return "Clone on Temic";
		case CTC_PAY: return "Apple/Goole Pay";
		case CTC_MOBILE: return "RgSec Mobile";
		default: return "Unknown card";
	}
}

void print_device_info_short(uint32_t index, const RG_DEVICE_INFO_EXT* pDeviceIndoExt) {
	printf("%d\tDevice '%s' Address: '%d' Serial: '%d' FW: %d.%d\n",
		index,
		device_type_to_device_name(pDeviceIndoExt->type), 
		pDeviceIndoExt->address, 
		pDeviceIndoExt->serial, 
		(pDeviceIndoExt->firmware >> 8) & 0xFF, pDeviceIndoExt->firmware & 0xFF);
}

constexpr char hexmap[] = {
	'0', '1', '2', '3', '4', '5', '6', '7',
	'8', '9', 'A', 'B', 'C', 'D', 'E', 'F'
};

std::string arr2hex(uint8_t* data, int len) {
	std::string s(len * 2, ' ');
	for (int i = 0; i < len; ++i) {
		s[2 * i] = hexmap[(data[i] & 0xF0) >> 4];
		s[2 * i + 1] = hexmap[data[i] & 0x0F];
	}
	return s;
}


typedef struct {
	uint8_t address;
} reader_info;

RG_ENDPOINT poll_endpoint = {};
reader_info poll_reader = {};
bool stop_thread = false;

int main(int argc, char* argv[]) {

	const auto version = RG_GetVersion();
	printf("ReadersSDK version: %d.%d\n", (version & 0xFFFF0000) >> 16, version & 0xFFFF);

	void* pvFoundEnpointsList = nullptr;
	uint32_t foundEnpointsListSize = 0;
	uint32_t error = EC_OK;
	if ((error = RG_FindEndPoints(&pvFoundEnpointsList, E_RG_ENDPOINT_TYPE::ET_SERIAL | ET_USBHID, &foundEnpointsListSize)) != EC_OK) {
		printf("RG_FindEndPoints fail... Error code: '%d'\n", error);
		return 1;
	}
	
	printf("Found '%d' endpoints\n", foundEnpointsListSize);
	if (foundEnpointsListSize <= 0) {
		return 1;
	}

	RG_ENDPOINT_INFO endpointInfo = {};
	for (uint32_t foundEnpointsListIndex = 0; foundEnpointsListIndex < foundEnpointsListSize; foundEnpointsListIndex++) {
		if((error = RG_GetFoundEndPointInfo(pvFoundEnpointsList, foundEnpointsListIndex, &endpointInfo)) != EC_OK) {
			printf("RG_GetFoundEndPointInfo fail... Error code: '%d'\n", error);
			return 1;
		}
		
		printf("%d:\t%s\t%s\n", foundEnpointsListIndex, endpoint_type_to_endpoint_name(endpointInfo.type), endpointInfo.address);
	}

	uint32_t selectedEndpointIndex = foundEnpointsListSize;
	while (true) {
		printf("Select endpoint (enter number): ");
		if (scanf("%u", &selectedEndpointIndex) == 1 && selectedEndpointIndex < foundEnpointsListSize) {
			RG_GetFoundEndPointInfo(pvFoundEnpointsList, selectedEndpointIndex, &endpointInfo);
			poll_endpoint.type = endpointInfo.type;
			poll_endpoint.address = endpointInfo.address;
			break;
		}
	}

	RG_CloseResource(pvFoundEnpointsList);

	std::vector<RG_DEVICE_INFO_EXT> foundDeviceList { 0 };
	size_t foundDevicesCount = 0;
	for (uint8_t deviceAddress = 0; deviceAddress <=  0; deviceAddress++) {
		RG_DEVICE_INFO_EXT deviceInfoExt = {};
		error = RG_GetInfoExt(&poll_endpoint, deviceAddress, &deviceInfoExt);
		if (error == EC_OK) {
			foundDeviceList.push_back(deviceInfoExt);
			foundDevicesCount++;
		}
	}

	printf("Found devices: %u\n", foundDevicesCount);
	if (foundDevicesCount == 0) {
		return 1;
	}

	for (size_t foundDeviceIndex = 0; foundDeviceIndex < foundDevicesCount; foundDeviceIndex++) {
		print_device_info_short(foundDeviceIndex, &foundDeviceList[foundDeviceIndex]);
	}

	uint32_t selectedFoundDeviceIndex = foundDevicesCount;
	uint8_t selectedAddress = 4;
	while (true) {
		printf("Select device (enter number): ");
		if (scanf("%u", &selectedFoundDeviceIndex) == 1 && selectedFoundDeviceIndex < foundDevicesCount) {
			poll_reader.address = foundDeviceList[selectedFoundDeviceIndex].address;
			break;
		}
	}

	if ((error = RG_InitDevice(&poll_endpoint, poll_reader.address)) != EC_OK) {
		printf("RG_InitDevice fail... Error code: '%d'\n", error);
		return 1;
	}


	if ((error = RG_SetCardsMask(&poll_endpoint, poll_reader.address, E_RG_CARD_FAMILY_CODE::CF_ALL)) != EC_OK) {
		printf("RG_SetCardsMask fail... Error code: '%d'\n", error);
		return 1;
	}


	void* l_reader_event_queue = nullptr;
	auto reader_events_mask = E_RG_DEVICE_EVENT_TYPE::DET_CARD_PLACED_EVENT | E_RG_DEVICE_EVENT_TYPE::DET_CARD_REMOVED_EVENT;

	if ((error = RG_Subscribe(&l_reader_event_queue, &poll_endpoint, poll_reader.address, reader_events_mask, nullptr)) != EC_OK) {
		printf("RG_Subscribe fail... Error code: '%d'\n", error);
		return 1;
	}

	while (true) {

		void* p_event_memory = nullptr;
		uint32_t event_type = 0;

		uint32_t error = RG_PollEvents(l_reader_event_queue, &event_type, &p_event_memory, 100);

		if (error == EC_INVALID_HANDLE) {
			printf("EC_INVALID_HANDLE\n", error);
			return 1;
		}

		if (error == EC_POLL_QUEUE_CLOSED) {
			printf("EC_POLL_QUEUE_CLOSED\n", error);
			return 1;
		}

		if (error == EC_INVALID_RESOURCE) {
			printf("EC_INVALID_RESOURCE\n", error);
			return 1;
		}

		if (error == EC_POLL_NO_EVENTS) {
			continue;
		}

		if (error != EC_OK) {
			printf("RG_PollEvents fail... Error code: '%d'\n", error);
			return 1;
		}

		switch (event_type)
		{
			case DET_CARD_PLACED_EVENT:
			{
				auto p_card_info = reinterpret_cast<RG_CARD_INFO*>(p_event_memory);
				printf("DET_CARD_PLACED_EVENT: %s %s.\n",
					card_type_code_to_card_type_name(p_card_info->type),
					arr2hex(p_card_info->uid, 7).c_str());
				break; 
			}
			case E_RG_DEVICE_EVENT_TYPE::DET_CARD_REMOVED_EVENT:
			{
				printf("DET_CARD_REMOVED_EVENT\n", error);
				break; 
			}
			default:
				break;
		}
	}
	
	return 0;
}
