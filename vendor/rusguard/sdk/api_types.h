#pragma once

#include <cstdint>

#pragma pack(push, 1)

/// <summary>
/// Тип подключения
/// </summary>
typedef enum _RG_ENDPOINT_TYPE : uint8_t {
	/// <summary>
	/// Что-то непонятное, неизвестное
	/// </summary>
	ET_UNKNOWN = 0x00,
	/// <summary>
	/// USB HID
	/// </summary>
	ET_USBHID,
	/// <summary>
	/// Последовательный порт
	/// </summary>
	ET_SERIAL
} E_RG_ENDPOINT_TYPE;

/// <summary>
/// Определяет тип и адрес конечной точки для подключения к устройству/устройствам
/// </summary>
typedef struct _RG_ENDPOINT {
	/// <summary>
	/// Тип конечной точки, согласно E_RG_ENDPOINT_TYPE
	/// Определяет используемый механизм подключения.
	/// </summary>
	uint8_t				type;
	/// <summary>
	/// Адрес конечной точки (нуль-терминированная ASCII строка)
	/// </summary>
	const char*			address;
} RG_ENDPOINT;

/// <summary>
/// Указатель на структуру конечной точки устройства
/// </summary>
typedef RG_ENDPOINT *PRG_ENDPOINT;

/// <summary>
/// Предоставляет данные для подключения к конечной точке. Содержит базовую
/// и расширенную информацию.
/// Данный тип используется при поиске портов/устройств как возвращаемый.
/// </summary>
typedef struct _RG_ENDPOINT_INFO {
	/// <summary>
	/// Тип конечной точки, согласно E_RG_CONNECTION_TYPE
	/// Определяет используемый механизм подключения.
	/// </summary>
	uint8_t				type;
	/// <summary>
	/// Адрес конечной точки (нуль-терминированная ASCII строка)
	/// Максимальная длина строки - 64 символа, включая завершающий \0
	/// </summary>
	char				address[64];
	/// <summary>
	/// Отображаемое (системное) имя конечной точки (нуль-терминированная ASCII строка)
	/// Максимальная длина строки - 128 символов, включая завершающий \0
	/// </summary>
	char				friendly_name[128];
} RG_ENDPOINT_INFO;

/// <summary>
/// Указатель на структуру конечной точки устройства
/// </summary>
typedef RG_ENDPOINT_INFO *PRG_ENDPOINT_INFO;

/// <summary>
/// Типы считывателей
/// </summary>
typedef enum _E_RG_DEVICE_TYPE : uint8_t {
	/// <summary>
	/// Считыватель R10-EHT
	/// </summary>
	DTE_R10EHT = 0x0A,
	/// <summary>
	/// Считыватель R10-MF
	/// </summary>
	DTE_R10MF = 0x0B,
	/// <summary>
	/// Считыватель R15 Multi
	/// </summary>
	DTE_R15MULTI = 0x0F,
	/// <summary>
	/// USB считыватель R5-USB Multi
	/// </summary>
	DTE_R5USBMULTI = 0x10,
	/// <summary>
	/// USB считыватель R5-USB Multi Prof
	/// </summary>
	DTE_R5USBMULTIPROF = 0x11,
	/// <summary>
	/// Биометрическский считыватель R10 MF BIO
	/// </summary>
	DTE_R10MF_BIO = 0x12,
	/// <summary>
	/// Считыватель с поддержкой чтения QR кодов R10 MF QR
	/// </summary>
	DTE_R10MF_QR = 0x13,
	/// <summary>
	/// Считыватель RDR204-EH Key
	/// </summary>
	DTE_RDR204EH = 0x0C,
	/// <summary>
	/// Считыватель RDR204-MF Key
	/// </summary>
	DTE_RDR204MF = 0x0D,
	/// <summary>
	/// Считыватель RDR-102
	/// </summary>
	DTE_RDR102 = 0x0E,
} E_RG_DEVICE_TYPE;

/// <summary>
/// Информация об устройстве (для 202)
/// </summary>
typedef struct _RG_DEVICE_INFO_SHORT {
	/// <summary>
	/// Адрес устройства
	/// </summary>
	uint8_t			address;
	/// <summary>
	/// Тип устройства
	/// </summary>
	uint8_t			type;
	/// <summary>
	/// Версия прошивки
	/// </summary>
	uint8_t			firmware;
	/// <summary>
	/// Количество записанных кодограмм
	/// </summary>
	uint8_t			codogramms;
} RG_DEVICE_INFO_SHORT, *PRG_DEVICE_INFO_SHORT;

/// <summary>
/// Информация об устройстве
/// </summary>
typedef struct _RG_DEVICE_INFO_EXT {
	/// <summary>
	/// Адрес устройства
	/// </summary>
	uint8_t			address;
	/// <summary>
	/// Серийный номер
	/// </summary>
	uint32_t		serial;
	/// <summary>
	/// Значение для проверки на запрет прошивки
	/// </summary>
	uint8_t			firmwareUpdateLock;
	/// <summary>
	/// Тип устройства
	/// </summary>
	uint8_t			type; 
	/// <summary>
	/// Версия прошивки
	/// </summary>
	uint16_t		firmware;
	/// <summary>
	/// Флаги функциональности устройства
	/// </summary>
	uint32_t		capabilities;
} RG_DEVICE_INFO_EXT, *PRG_DEVICE_INFO_EXT;


/// <summary>
/// Флаги функциональности
/// </summary>
typedef enum _E_RG_CAPABILITIES : uint32_t {
	CFE_SUPPORT_HID_EM = 1,
	CFE_SUPPORT_TEMIC = 2,
	CFE_SUPPORT_COTAG = 4,
	CFE_SUPPORT_MIFARE = 8,

	CFE_SUPPORT_INF = 16,
	CFE_SUPPORT_NFC = 32,
	CFE_SUPPORT_NFC_PAY = 64,
	CFE_SUPPORT_BLE = 128,

	CFE_SUPPORT_TM_W = 256,
	CFE_SUPPORT_RBUS = 512,
	CFE_SUPPORT_RS485 = 1024,
	CFE_SUPPORT_USB = 2048,

	CFE_HAS_MEMORY = 4096,
	CFE_HAS_KEYBOARD = 8192,
	CFE_HAS_CLOCK = 16384,
	CFE_HAS_TERMO = 32768,

	CFE_HAS_RELAY = 65536,
	CFE_READER = 131072,
	CFE_CONTROLLER = 262144,
	CFE_SUPPORT_ODSP = 524288,
} E_RG_CAPABILITIES;

typedef enum _E_RG_STATUS_TYPE : uint8_t {
	STE_UNKNOWN = 0,
	/// <summary>
	/// Нет приложенной карты
	/// </summary>
	STE_NO_CARD = 1,
	/// <summary>
	/// Карта без памяти или нет профилей в памяти
	/// </summary>
	STE_CARD = 9,
	/// <summary>
	/// Карта с памятью, но произошла ошибка доступа к памяти
	/// </summary>
	STE_CARD_NO_AUTH = 10,
	/// <summary>
	/// Карта с памятью и успешная авторизация
	/// </summary>
	STE_CARD_AUTH = 26
} E_RG_STATUS_TYPE;

/// <summary>
/// Коды семейств карт
/// </summary>
typedef enum _E_RG_CARD_FAMILY_CODE : uint8_t {
	/// <summary>
	/// Код с клавиатуры
	/// </summary>
	CF_PIN = 1,
	/// <summary>
	/// Temic
	/// </summary>
	CF_TEMIC = 2,
	/// <summary>
	/// HID
	/// </summary>
	CF_HID = 4,
	/// <summary>
	/// Em-Marine
	/// </summary>
	CF_EM = 8,
	/// <summary>
	/// Indala
	/// </summary>
	CF_INDALA = 16,
	/// <summary>
	/// Cotag/Bewator
	/// </summary>
	CF_COTAG = 32,
	/// <summary>
	/// Mifare
	/// </summary>
	CF_MIFARE = 64,
	/// <summary>
	/// Indala MT
	/// </summary>
	CF_INDALA_MT = 128,
	/// <summary>
	/// Все карты
	/// </summary>
	CF_ALL = 255
} E_RG_CARD_FAMILY_CODE;

/// <summary>
/// Коды типов карт
/// </summary>
typedef enum _E_RG_CARD_TYPE_CODE : uint8_t {
	/// <summary>
	/// PIN код склавиатуры
	/// </summary>
	CTC_PIN = 0x00,
	/// <summary>
	/// Карта Temic
	/// </summary>
	CTC_TEMIC = 0x01,
	/// <summary>
	/// Карта HID
	/// </summary>
	CTC_HID = 0x02,
	/// <summary>
	/// Карта Em-Marine
	/// </summary>
	CTC_EM = 0x03,
	/// <summary>
	/// Карта Indala
	/// </summary>
	CTC_INDALA = 0x04,
	/// <summary>
	/// Карта COTAG
	/// </summary>
	CTC_COTAG = 0x05,
	/// <summary>
	/// Карта MIFARE DESFire EV1
	/// </summary>
	CTC_MF_DESFIRE = 0x06,
	/// <summary>
	/// Карта MIFARE Ultralight
	/// </summary>
	CTC_MF_UL = 0x07,
	/// <summary>
	/// Карта MIFARE Mini
	/// </summary>
	CTC_MF_MINI = 0x08,
	/// <summary>
	/// Карта MIFARE Classic 1K / MIFARE Plus EV1 2K SL1
	/// </summary>
	CTC_MF_CL1K_PL2K = 0x09,
	/// <summary>
	/// Карта MIFARE Classic 4K / MIFARE Plus EV1 4K SL1
	/// </summary>
	CTC_MF_CL4K_PL4K = 0x0A,
	/// <summary>
	/// Карта MIFARE Plus 2K SL2
	/// </summary>
	CTC_MF_PL2K_SL2 = 0x0B,
	/// <summary>
	/// Карта MIFARE Plus 4K SL2
	/// </summary>
	CTC_MF_PL4K_SL2 = 0x0C,
	/// <summary>
	/// Карта MIFARE Plus SL3
	/// </summary>
	CTC_MF_SL3 = 0x0D,
	/// <summary>
	/// Карта SmartMX 4K
	/// </summary>
	CTC_SMX4K = 0x0E,
	/// <summary>
	/// Карта SmartMX 1K
	/// </summary>
	CTC_SMX1K = 0x0F,
    /// <summary>
    /// Клон на Temic
    /// </summary>
	CTC_CLONE_ON_TEMIC = 0x40,
	/// <summary>
	/// Мобила с PAY
	/// </summary>
	CTC_PAY = 0xFD,
	/// <summary>
	/// Мобила с приложением
	/// </summary>
	CTC_MOBILE = 0xFE

} E_RG_CARD_TYPE_CODE;

/// <summary>
/// Информация о карте
/// </summary>
typedef struct _RG_CARD_INFO {
	/// <summary>
	/// Тип карты, согласно E_RG_CARD_TYPE_CODE
	/// </summary>
	uint8_t type;
	/// <summary>
	/// UID карты
	/// </summary>
	uint8_t uid[7];
} RG_CARD_INFO, *PRG_CARD_INFO;

/// <summary>
/// Структура данных с блока карты
/// </summary>
typedef struct _RG_CARD_MEMORY {
	/// <summary>
	/// Номер профиля или номер блока, в зависимости от места использования
	/// </summary>
	uint8_t profile_block;
	/// <summary>
	/// Данные блока
	/// </summary>
	uint8_t block_data[16];
} RG_CARD_MEMORY, *PRG_CARD_MEMORY;

/// <summary>
/// Флаги определяющие механизм авторизации карт Mifare
/// </summary>
typedef enum _E_RG_CARD_AUTH_FLAGS : uint8_t {	
	DEFAULT = 0,
	/// <summary>
	/// Если установлен, авторизация Mifare Classic будет произодиться по ключу B. Иначе по ключу А
	/// </summary>
	CAF_CLASSIC_KEY_B = 1,
	/// <summary>
	/// При работе профиля с Pay/приложением.
	/// Включает использоние сгенерированного ключа
	/// </summary>
	CAF_GENERATED_KEY = 1,
	/// <summary>
	/// Если установлен, авторизация Mifare Plus будет произодиться по ключу B. Иначе по ключу А
	/// </summary>
	CAF_PLUS_KEY_B = 2,
	/// <summary>
	/// При работе профиля с Pay/приложением.
	/// Включает использоние заданного ключа
	/// </summary>
	CAF_PRESENT_KEY = 2,
	/// <summary>
	/// Если установлен, будет использован механизм авторизации для карты SL3, иначе SL1/CLassic
	/// </summary>
	CAF_PLUS_SL3 = 4,
	/// <summary>
	/// При работе профиля с Pay/приложением.
	/// Включает использоние эмитированного ключа
	/// </summary>
	CAF_EMITED_KEY = 4,	
	/// <summary>
	/// Профиль используется для работы с Pay
	/// Взаимоисключающий с CAF_USE_APP
	/// </summary>
	CAF_USE_PAY = 32,
	/// <summary>
	/// Профиль используется для работы с мобильным приложением
	/// Взаимоисключающий с CAF_USE_PAY
	/// </summary>
	CAF_USE_APP = 64
} E_RG_CARD_AUTH_FLAGS;

/// <summary>
/// Структур параметров авторизации карт Mifare
/// </summary>
typedef struct _RG_CARD_AUTH_PARAMS {
	/// <summary>
	/// Флаги авторизации, согласно E_RG_CARD_AUTH_FLAGS
	/// </summary>
	uint8_t flags;
	/// <summary>
	/// Ключ авторизации карт Mifare Classic
	/// </summary>
	uint8_t classicKey[6];
	/// <summary>
	/// Ключ авторизации карт Mifare Plus SL3
	/// </summary>
	uint8_t plusKey[16];
} RG_CARD_AUTH_PARAMS, *PRG_CARD_AUTH_PARAMS;

/// <summary>
/// СТруктура определяющая длинну и тело кодограммы
/// </summary>
typedef struct _RG_CODOGRAMM {
	/// <summary>
	/// Длинна кодограммы в битах (0...32, 1бит = 100мс индикации)
	/// </summary>
	uint8_t length;
	/// <summary>
	/// Тело кодограммы, (1бит = 100мс индикации)
	/// </summary>
	uint32_t body;
} RG_CODOGRAMM, *PRG_CODOGRAMM;

/// <summary>
/// Приоритет выполнения кодограммы
/// </summary>
typedef enum _E_RG_CODOGRAMM_PRIORITY : uint8_t {
	/// <summary>
	/// Фоновая индикация
	/// </summary>
	CPE_BACKGROUND = 0,
	/// <summary>
	/// Циклическая индикация
	/// </summary>
	CPE_CYCLIC_LO,
	/// <summary>
	/// Циклическая индикация с вышим приоритетом
	/// </summary>
	CPE_CYCLIC_HI,
	/// <summary>
	/// Разовая индикация
	/// </summary>
	CPE_ONCE_LO,
	/// <summary>
	/// Разовая индикация с высшим приоритетом
	/// </summary>
	CPE_ONCE_HI
} E_RG_CODOGRAMM_PRIORITY;

/// <summary>
/// Идентификаторы событий
/// </summary>
typedef enum _E_RG_DEVICE_EVENT_TYPE : uint32_t {
	DET_UNKNOWN_EVENT = 0,
	/// <summary>
	/// К считывателю приложена карта.
	/// В качестве данных события возвращает указатель на RG_CARD_INFO
	/// </summary>
	DET_CARD_PLACED_EVENT = 2,
	/// <summary>
	/// Карта убрана из поля считывателя
	/// В качестве данных события возвращает nullptr
	/// </summary>
	DET_CARD_REMOVED_EVENT = 4,
	/// <summary>
	/// Изменилось состояние реле (клемма EK).
	/// В данных - указатель на int8_t, где:
	/// 0й бит - новое состояние на момент фикасации события
	/// 1й бит - текущее состояние на момент фиксации события
	/// </summary>
	DET_RELAY_STATE_CHANGED = 8,
	/// <summary>
	/// Изменилось состояние тампера
	/// В данных - указатель на int8_t, где:
	/// 0й бит - новое состояние на момент фикасации события
	/// 1й бит - текущее состояние на момент фиксации события
	/// </summary>
	DET_TAMPER_STATE_CHANGED = 16,
	/// <summary>
	/// Изменилось состояние кнопки (клемма SYN).
	/// В данных - указатель на int8_t, где:
	/// 0й бит - новое состояние на момент фикасации события
	/// 1й бит - текущее состояние на момент фиксации события
	/// </summary>
	DET_BUTTON_STATE_CHANGED = 32,
	/// <summary>
	/// Изменилось состояние датчика двери (клемма SN).
	/// В данных - указатель на int8_t, где:
	/// 0й бит - новое состояние на момент фикасации события
	/// 1й бит - текущее состояние на момент фиксации события
	/// </summary>
	DET_DOOR_SENSOR_STATE_CHANGED = 64,
	/// <summary>
	/// Ошибка в процессе опроса устройства
	/// В данных - указатель на uint32_t, содержащий код ошибки
	/// </summary>
	DET_POLL_ERROR = 128,

} E_RG_DEVICE_EVENT_TYPE;


/// <summary>
/// Определяет тип выполняемого дествия по PIN коду
/// </summary>
typedef enum _E_RG_PIN_ACTION_TYPE : uint8_t {
	/// <summary>
	/// Разблокировка доступак блоку параметров
	/// </summary>
	EPA_UNLOCK = 0,	
	/// <summary>
	/// Сохранение внесенных изменений в память устройства
	/// </summary>
	EPA_STORE
} E_RG_PIN_ACTION_TYPE;

/// <summary>
/// Определяет типы блоков параметров в памяти устройства
/// </summary>
typedef enum _E_RG_SETTINGS_BLOCK_TYPE : uint8_t {
	/// <summary>
	/// Блок настроек
	/// </summary>
	ESB_SETTINGS = 0,
	/// <summary>
	/// Блок профилей
	/// </summary>
	ESB_PROFILES,	
	/// <summary>
	/// Блок ключей
	/// </summary>
	ESB_KEYS
} E_RG_SETTINGS_BLOCK_TYPE;

typedef enum _E_RG_KEY_TYPE : uint8_t {
	/// <summary>
	/// Использовать ключ A для Mifare Classic
	/// </summary>
	EKT_MC_KEY_A = 0x00,
	/// <summary>
	/// Использовать ключ A для Mifare Plus
	/// </summary>
	EKT_MP_KEY_A = 0x08,
	/// <summary>
	/// Использовать ключ B для Mifare Classic
	/// </summary>
	EKT_MC_KEY_B = 0x01,
	/// <summary>
	/// Использовать ключ B для Mifare Plus
	/// </summary>
	EKT_MP_KEY_B = 0x09,
} RG_KEY_TYPE;

#pragma pack(pop) // reset pack 1
