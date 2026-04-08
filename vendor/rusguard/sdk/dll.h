#pragma once

#if defined(__linux) || defined(__linux__) || defined(linux)
#define API_EXPORT extern "C" __attribute__((visibility("default")))
#define API_IMPORT extern "C" __attribute__((visibility("hidden")))
#elif defined(_WIN32) || defined(__WIN32__) || defined(WIN32) || defined(_WIN64)
#define API_EXPORT extern "C" __declspec(dllexport)
#define API_IMPORT extern "C" __declspec(dllimport)
#else
#define API_EXPORT
#define API_IMPORT
#endif

#ifdef LIB_IMPORT
#define API_METHOD API_IMPORT
#else
#define API_METHOD API_EXPORT
#endif

#ifndef CALL_CONV
#if defined(__linux) || defined(__linux__) || defined(linux)
#define CALL_CONV
#else
#define CALL_CONV _cdecl
#endif
#endif

#include "api_types.h"

API_EXPORT uint32_t CALL_CONV
RG_GetVersion();

/// <summary>
/// Выполняет инициализацию внутренних механизмов библиотеки.
/// </summary>
API_EXPORT uint32_t CALL_CONV
RG_InitializeLib();

/// <summary>
/// Завершает работу внутренних механизмов библиотеки.
/// </summary>
/// <returns></returns>
API_METHOD uint32_t  CALL_CONV
RG_Uninitialize();

/// <summary>
/// Закрывает и уничтожает ранее выделенный ресурс по указанному дескриптору.
/// </summary>
/// <param name="handle">Дескриптор ресурса.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_CloseResource(void* handle);

/// <summary>
/// Выполняет поиск доступных точек подключения.
/// </summary>
/// <param name="pEndPointListHandle">Указатель на переменную, в которомю будет записан дескриптор списка найденных точек подключения.</param>
/// <param name="pCount">Маска типов конечных точек.</param>
/// <param name="pCount">Указатель на переменную, по которому будет сохранено колличество элементов в списке результатов.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_FindEndPoints(void** pEndPointListHandle, uint8_t enpointTypeMask, uint32_t* pCount);

/// <summary>
/// Извлекает из списка результатов, полученного с помощью функции RG_GetEndpointList, информацию о точке подключения по указанному индексу.
/// </summary>
/// <param name="endPointListHandle">Дескриптор списка точек подключения, полученный через RG_GetEndpointList.</param>
/// <param name="listIndex">Индекс в списке.</param>
/// <param name="pEndpointInfo">Указатель на структуру информации о точке подключения.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_GetFoundEndPointInfo(void* endPointListHandle, uint32_t listIndex, PRG_ENDPOINT_INFO pEndpointInfo);

/// <summary>
/// Выполняет поиск устройств по всем доступным точкам подключения.
/// </summary>
/// <param name="pDevicesListHandle">Указатель на переменную, в которомю будет записан дескриптор списка найденных устройств.</param>
/// <param name="pCount">Указатель на переменную, по которому будет сохранено колличество элементов в списке результатов.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_FindDevices(void** pDevicesListHandle, uint8_t endpointTypeMask, uint32_t* pCount);

/// <summary>
/// Извлекает из списка результатов, полученного с помощью функции RG_GetDevicesList, информацию об устройстве по индексу.
/// </summary>
/// <param name="deviceListHandle">Дескриптор списка найденных устройств, полученный через RG_GetDevicesList.</param>
/// <param name="listIndex">Индекс в списке.</param>
/// <param name="pEndpointInfo">Указатель на структуру информации о точке подключения.</param>
/// <param name="pDeviceInfoExt">Указатель на структуру расширенной информации об устройстве.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_GetFoundDeviceInfo(void* deviceListHandle, uint32_t ListIndex, PRG_ENDPOINT_INFO pEndpointInfo, PRG_DEVICE_INFO_EXT pDeviceInfoExt);

/// <summary>
/// Инициализация устройства.
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_InitDevice(PRG_ENDPOINT pEndPoint, uint8_t address);

/// <summary>
/// Сбрасывает состояние устройства. Потребуется повторная инициализация.
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_CloseDevice(PRG_ENDPOINT pEndPoint, uint8_t address);

/// <summary>
/// Запрос информации об устройстве. Требуется предварительная инициализация устройства методом RG_InitDevice.
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="pDeviceInfo">Указатель на структуру информации об устройстве.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_GetInfo(PRG_ENDPOINT pEndPoint, uint8_t address, PRG_DEVICE_INFO_SHORT pDeviceInfo);

/// <summary>
/// Запрос расширенной информации об устройстве.
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="pDeviceInfo">Указатель на структуру расширенной информации об устройстве.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_GetInfoExt(PRG_ENDPOINT pEndPoint, uint8_t address, PRG_DEVICE_INFO_EXT pDeviceInfo);

/// <summary>
/// Задает для устройство типы считываемых карт. Требуется предварительная инициализация устройства методом RG_InitDevice.
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="mCardsFamilyMask">Маска типов считываемых карт, согласно E_RG_CARD_FAMILY_CODE.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_SetCardsMask(PRG_ENDPOINT pEndPoint, uint8_t address, uint8_t mCardsFamilyMask);

/// <summary>
/// Удаляет все профили из памяти устройства. Требуется предварительная инициализация устройства методом RG_InitDevice.
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_ClearProfiles(PRG_ENDPOINT pEndPoint, uint8_t address);

/// <summary>
/// Записывает профиль в память устройства. Требуется предварительная инициализация устройства методом RG_InitDevice.
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="mProfileNum">Номер профиля, под которым он будет записан в память устройства.</param>
/// <param name="mBlockNum">Номер блока карты.</param>
/// <param name="pCardAuthParams">Указатель на структуру параметров авторизации карты.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_WriteProfile(PRG_ENDPOINT pEndPoint, uint8_t address, uint8_t profileNum, uint8_t blockNum, PRG_CARD_AUTH_PARAMS pCardAuthParams);

/// <summary>
/// Записывает кодограмму в память устройства. Требуется предварительная инициализация устройства методом RG_InitDevice.
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="mCodogrammNum">Номер кодограммы, под которым она будет записана в память устройства.</param>
/// <param name="pCodogramm">Указатель на структуру представляющую кодограмму.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_WriteCodogramm(PRG_ENDPOINT pEndPoint, uint8_t address, uint8_t codogrammNum, PRG_CODOGRAMM pCodogramm);

/// <summary>
/// Запускает выполнение кодограмм на указанных каналах индикации на заданнном уровне приоритета.
/// Требуется предварительная инициализация устройства методом RG_InitDevice.
/// Кодограммы должны быть записаны в память устройства методом RG_WriteCodogramm
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="priority">Приоритет выполнения.</param>
/// <param name="sChannelNum">Номер кодограммы для звукового канала.</param>
/// <param name="rChannelNum">Номер кодограммы для красного канала.</param>
/// <param name="gChannelNum">Номер кодограммы для зеленого канала.</param>
/// <param name="bChannelNum">Номер кодограммы для синего канала.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_StartCodogramm(PRG_ENDPOINT pEndPoint, uint8_t address, uint8_t priority, uint8_t sChannelNum, uint8_t rChannelNum, uint8_t gChannelNum, uint8_t bChannelNum);

/// <summary>
/// Записывает данные в блок памяти карты по указанному номеру профиля.
/// Требуется предварительная инициализация устройства методом RG_InitDevice.
/// Профиль должен быть предварительно записан в память устройства методом RG_WriteProfile.
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="pMemory">Указатель на структуру данных блока памяти. Намоер профиля указывается в pMemory->profile_block.</param>
/// <returns>Код ошибки</returns>
API_METHOD uint32_t CALL_CONV
RG_WriteBlock(PRG_ENDPOINT pEndPoint, uint8_t address, PRG_CARD_MEMORY pMemory);

/// <summary>
/// Записывает данные в указанный блок памяти карты используя указанные параметры авторизации.
/// Требуется предварительная инициализация устройства методом RG_InitDevice.
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="pMemory">Указатель на структуру данных блока памяти. Намер блока указывается в pMemory->profile_block.</param>
/// <param name="pCardAuthParams">Указатель на структуру параметров авторизации карты.</param>
/// <returns>Код ошибки</returns>
API_METHOD uint32_t CALL_CONV
RG_WriteBlockDirect(PRG_ENDPOINT pEndPoint, uint8_t address, PRG_CARD_MEMORY pMemory, PRG_CARD_AUTH_PARAMS pCardAuthParams);

/// <summary>
/// Считывает данные из указаннного блока памяти карты используя указанные параметры авторизации.
/// Требуется предварительная инициализация устройства методом RG_InitDevice.
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="pMemory">Указатель на структуру данных блока памяти. Намер блока указывается в pMemory->profile_block.</param>
/// <param name="pCardAuthParams">Указатель на структуру параметров авторизации карты.</param>
/// <returns>Код ошибки</returns>
API_METHOD uint32_t CALL_CONV
RG_ReadBlockDirect(PRG_ENDPOINT pEndPoint, uint8_t address, PRG_CARD_MEMORY pMemory, PRG_CARD_AUTH_PARAMS pCardAuthParams);

/// <summary>
/// Считывает данные из указаннного блока памяти карты используя указанные параметры авторизации.
/// Требуется предварительная инициализация устройства методом RG_InitDevice.
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="pStatusType">Указатель на переменную, по которому будет записано текущее значение татуса.</param>
/// <param name="pPinStates">Указатель на переменную, по которому будут записаны флаги текущего состояния входов/выходов.</param>
/// <param name="pCardInfo">Указатель на структуру информации о карте, заполняется в зависимости от текущего статуса.</param>
/// <param name="pMemory">Указатель на структуру данных, считанных из блока памяти карты при успешной авторизации по профилю. Номер профиля сохраняется в pMemory->profile_block.</param>
/// <returns>Код ошибки</returns>
API_METHOD uint32_t CALL_CONV
RG_GetStatus(PRG_ENDPOINT pEndPoint, uint8_t address, uint8_t* pStatusType, uint8_t* pPinStates, PRG_CARD_INFO pCardInfo, PRG_CARD_MEMORY pMemory);

/// <summary>
/// Считывает данные из указаннного блока памяти карты используя указанные параметры авторизации.
/// Требуется предварительная инициализация устройства методом RG_InitDevice.
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="pStatusType">Указатель на переменную, по которому будет записано текущее значение татуса.</param>
/// <param name="pUidBuffer">Указатель на блок памяти, для хранения UID.</param>
/// <param name="uidBufferSize">Размер блока памяти по указателю pUidBuffer.</param>
/// <param name="pUidSize">Указатель на переменную, в котрую будет записан размер UID карты.</param>
/// <returns>Код ошибки</returns>
API_METHOD uint32_t CALL_CONV
RG_GetCard(PRG_ENDPOINT pEndPoint, uint8_t address, uint8_t* pStatusType, uint8_t* pUidBuffer, int32_t uidBufferSize, int32_t*
           pUidSize);


/// <summary>
/// Подписка на события устройства согласно маске.
/// </summary>
/// <param name="pDeviceEventsQueue">Указатель на переменную, в которомю будет записан дескриптор очереди событий устройства для текущей подписки.</param>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="eventsMask">Маска типов событий устройства.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_Subscribe(void** pDeviceEventsQueue, PRG_ENDPOINT pEndPoint, uint8_t address, uint32_t eventsMask, void* systeEventHandle);

/// <summary>
/// Извелкает событие из очереди событий устройства или ожидает поступления нового события при пустой очереди.
/// </summary>
/// <param name="deviceEventsQueue">Дескриптор очереди событий устройства.</param>
/// <param name="pEventType">Указатель на переменную, в которую будет записан тип извлеченного события.</param>
/// <param name="pEventMem">Указатель на указатель на область памяти, по которому будет аписан адрес текущего экземпляра события.</param>
/// <param name="pollWaitTimeoutMs">Время ожидания при отсутствии новых событий в очереди.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_PollEvents(void* deviceEventsQueue, uint32_t* pEventType, void** pEventMem, uint32_t pollWaitTimeoutMs);

/// <summary>
/// Изолирует устройство от потока опроса
/// Требуется предварительная инициализация устройства методом RG_InitDevice.
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <returns>Код ошибки</returns>
API_METHOD uint32_t CALL_CONV
RG_IsolateDevice(PRG_ENDPOINT pEndPoint, uint8_t address);

/// <summary>
/// Снимает изоляцию с устройства
/// Требуется предварительная инициализация устройства методом RG_InitDevice.
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <returns>Код ошибки</returns>
API_METHOD uint32_t CALL_CONV
RG_ResetIsolation(PRG_ENDPOINT pEndPoint, uint8_t address);

/// <summary>
/// Задает состояние управляющего выхода/порта по его номеру на указанное время.
/// Требуется предварительная инициализация устройства методом RG_InitDevice.
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="mAddress">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="outputNum">Номер выхода.</param>
/// <param name="state">Новое состояние. Если указано <c>true</c> выход будет подключени к подтяжке, иначе - к земле.</param>
/// <param name="timeSec">Время переключения в секундах, 0 = постоянно.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_SetControlOutputState(PRG_ENDPOINT pEndPoint, uint8_t mAddress, uint8_t outputNum, bool state, uint8_t timeSec);

/// <summary>
/// Сбрасывает поле на время, достаточное для переключения карты из одного режима в другой (например, при переключении из SL1 в SL3) и других операций
/// Требуется предварительная инициализация устройства методом RG_InitDevice.
/// При наличии активных подписок на события, требуется вызов RG_IsolateDevice().
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="mAddress">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_ResetField(PRG_ENDPOINT pEndPoint, uint8_t mAddress);

/// <summary>
/// Выполняет цикл запроса карт в поле, процедуру антиколлизии и выбор карты.
/// Требуется предварительная инициализация устройства методом RG_InitDevice.
/// При наличии активных подписок на события, требуется вызов RG_IsolateDevice().
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="pSak">Указатель на переменную для записи кода SAK (Select Acknowledge)</param>
/// <param name="pAtqa">Указатель на переменную для записи кода типа карты Mifare.</param>
/// <param name="pUidBuf">Указатель на блок памяти для сохранения UID выбранной карты.</param>
/// <param name="uidBufSize">Размер блока памяти по указателю pUidBufSize.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_Iso_Ras(PRG_ENDPOINT pEndPoint, uint8_t address, uint16_t* pSak, uint16_t* pAtqa, uint8_t* pUidBuf, int32_t uidBufSize);

/// <summary>
/// Выполняет команду перехода на обмен по ISO 14443-4
/// Требуется предварительная инициализация устройства методом RG_InitDevice.
/// При наличии активных подписок на события, требуется вызов RG_IsolateDevice().
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="pAtsBuf">Указатель на блок памяти для записи UID выбранной карты.</param>
/// <param name="atsBufSize">Размер блока памяти по указателю pAtsBuf</param>
/// <param name="pAtsSize">Указатель на переменную, для записи количества байт, сохраненных в pAtsBuf.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_Iso_Rats(PRG_ENDPOINT pEndPoint, uint8_t address, uint8_t* pAtsBuf, int32_t atsBufSize, int32_t* pAtsSize);

/// <summary>
/// Выполняет произвольную передачу данных по протоколу ISO14443-4.
/// Требуется предварительная инициализация устройства методом RG_InitDevice.
/// При наличии активных подписок на события, требуется вызов RG_IsolateDevice().
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="pReqBuf">Указатель на блок памяти, в котором хранятся передаваемые данные.</param>
/// <param name="reqBufSize">Размер блока памяти по указателю pDataBuf.</param>
/// <param name="pRespBuf">Указатель на блок памяти, в который будет зхаписан ответ на переданное сообщение.</param>
/// <param name="respBufSize">Размер блока памяти по указателю respBufSize.</param>
/// <param name="pRespSize">Указатель на переменную, для записи количества байт, сохраненных в pRespBuf.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_Iso_Exchange(PRG_ENDPOINT pEndPoint, uint8_t address, const uint8_t* pReqBuf, int32_t reqBufSize, uint8_t* pRespBuf, int32_t
                respBufSize, int32_t* pRespSize);

/// <summary>
/// Авторизация сектора карты Mifare.
/// Требуется предварительная инициализация устройства методом RG_InitDevice.
/// При наличии активных подписок на события, требуется вызов RG_IsolateDevice().
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="mAddress">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="blockNum">Номер блока сектора, в который производится авторизация.</param>
/// <param name="pKeyBuf">Указатель на блок памяти с данными ключа авторизации.</param>
/// <param name="keyBufSize">Размер блока памяти/данных по указателю pKeyBuf (максимально допустимая длинна ключа - 16 байт).</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_Iso_Auth(PRG_ENDPOINT pEndPoint, uint8_t mAddress, uint16_t blockNum, const uint8_t* pKeyBuf, int32_t keyBufSize);

/// <summary>
/// Выполняет авторизацию сектора карты Mifare Classic
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="mAddress">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="blockNum">Номер блока сектора, в который производится авторизация.</param>
/// <param name="keyType">Тип используемого ключа авторизации (A/B).</param>
/// <param name="pKeyBuf">Указатель на блок памяти, содержащей, как минимум, 6 байт данныхъ ключа авторизации.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_MF_AuthorizeClassic(PRG_ENDPOINT pEndPoint, uint8_t mAddress, uint8_t blockNum, uint8_t keyType, uint8_t* pKeyBuf);

/// <summary>
/// Выполняет чтение данных из блока памяти карты Mifare Classic/Plus
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="mAddress">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="flags">ФЛаги определяющие тип карты, с которой производится чтение.</param>
/// <param name="blockNum">Номер блока карты.</param>
/// <param name="pDataBuf">Указатель на блок памяти, в которую будут записаны данные считанные из блока памяти карты.</param>
/// <param name="dataBufSize">Размер блока памяти по указателю pDataBuf.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_MF_ReadBlock(PRG_ENDPOINT pEndPoint, uint8_t mAddress, uint8_t blockNum, uint8_t flags, uint8_t* pDataBuf, int32_t dataBufSize);

/// <summary>
/// Выполняет запись данных в блок памяти карты Mifare Classic/Plus
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="mAddress">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="flags">Флаги определяющие тип карты, в память которой производится запись (Classic/Plus).</param>
/// <param name="blockNum">Номер блока карты.</param>
/// <param name="pDataBuf">Указатель на блок памяти содержащей данные, которые необходимо записать в блок памяти карты.</param>
/// <param name="dataBufSize">Размер блока памяти по указателю pDataBuf.</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_MF_WriteBlock(PRG_ENDPOINT pEndPoint, uint8_t mAddress, uint8_t blockNum, uint8_t flags, uint8_t* pDataBuf, int32_t dataBufSize);

/// <summary>
/// Выполняет передачу PIN-кода защиты параметров
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="pin">PIN-код</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_UnlockSettigns(PRG_ENDPOINT pEndPoint, uint8_t address, uint16_t pin);

/// <summary>
/// Выполняет передачу PIN-кода защиты параметров
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="pin">PIN-код</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_CommitSettings(PRG_ENDPOINT pEndPoint, uint8_t address, uint16_t pin);

/// <summary>
/// Выполняет чтение блока параметров
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="blockType">Тип блока параметров, согласно E_RG_SETTINGS_BLOCK_TYPE</param>
/// <param name="blockNum">Номер блока/профиля</param>
/// <param name="block32Buf">Указатель на область памяти, куда будет произведено чтение данных блока из памяти устройства</param>
/// <param name="block32BufSize">Размер блока памяти по указателю pBlockData</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_ReadSettingsBlock(PRG_ENDPOINT pEndPoint, uint8_t address, uint8_t blockType, uint16_t blockNum, uint8_t* block32Buf, int32_t
                     block32BufSize);

/// <summary>
/// Выполняет запись блока параметров
/// </summary>
/// <param name="pEndPoint">Указатель на структуру параметров подключения.</param>
/// <param name="address">Адрес устройства (0...3, в зависимости от типа подключения).</param>
/// <param name="blockType">Тип блока параметров, согласно E_RG_SETTINGS_BLOCK_TYPE</param>
/// <param name="blockNum">Номер блока/профиля</param>
/// <param name="block32Buf">Указатель на область памяти с данными блока параметров, которые требуется записать, не более 32 байт.</param>
/// <param name="block32BufSize">Размер блока памяти по указателю pBlockData</param>
/// <returns></returns>
API_METHOD uint32_t CALL_CONV
RG_WriteSettingsBlock(PRG_ENDPOINT pEndPoint, uint8_t address, uint8_t blockType, uint16_t blockNum, uint8_t* block32Buf, int32_t
                      block32BufSize);



API_METHOD uint32_t CALL_CONV
RG_UpdateFirmware(PRG_ENDPOINT pEndPoint, uint8_t mAddress, const char* fwFilePath, void (*firmwarecb)(uint8_t mode, uint16_t currentBlock, uint16_t totalBlocks, uint32_t error));

API_METHOD uint32_t CALL_CONV
RG_FP_EnrollAndStoreRam(PRG_ENDPOINT pEndPoint, uint8_t mAddress);

API_METHOD uint32_t CALL_CONV
RG_FP_ReadEnroll(PRG_ENDPOINT pEndPoint, uint8_t mAddress, uint8_t* enrollBuffer, int32_t enrollBufferSize);

API_METHOD uint32_t CALL_CONV
RG_FP_ReadEnrollToFile(PRG_ENDPOINT pEndPoint, uint8_t mAddress, const char* enrollFilePath);
