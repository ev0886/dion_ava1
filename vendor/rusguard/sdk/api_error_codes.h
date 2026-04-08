#pragma once

#include <cstdint>

typedef uint32_t api_error;

/// <summary>
/// Код ошибок API
/// </summary>
typedef enum _E_API_ERROR_CODES : api_error {
	/// <summary>
	/// Все хорошо
	/// </summary>
	EC_OK = 0,
	/// <summary>
	/// Все плохо
	/// </summary>
	EC_FAIL, // 1
	/// <summary>
	/// Функциональность не реализована
	/// </summary>
	EC_NOT_IMPLEMENTED, // 2
	/// <summary>
	/// Неверно задан один из аргументов
	/// </summary>
	EC_BAD_ARGUMENT, // 3
	/// <summary>
	/// Указан невалидный дескриптор ресурса, или ресурс закрыт
	/// </summary>
	EC_INVALID_HANDLE, // 4
	/// <summary>
	/// Указан дескриптор несовместимого ресурса
	/// </summary>
	EC_INVALID_RESOURCE, // 5
	/// <summary>
	/// Указан неподдерживаемый тип соединения
	/// </summary>
	EC_INVALID_CONNECTION_TYPE, // 6
	/// <summary>
	/// Адрес подключения не соответствует типу подключения
	/// </summary>
	EC_INVALID_CONNECTION_ADDRESS, // 7
	/// <summary>
	/// Указанный аддрес устройства является недопустимым для указанного типа подключения
	/// </summary>
	EC_INVALID_DEVICE_ADDRESS, // 8
	/// <summary>
	/// Функциональность не поддерживается целевым устройством
	/// </summary>
	EC_DEVICE_OPERATION_UNSUPPORTED, // 9
	/// <summary>
	/// Устройство было отключено в процессе обмена (для USB устройств).
	/// </summary>
	EC_DEVICE_NOT_CONNECTED, // 10
	/// <summary>
	/// Устройство не отвечает на запросы
	/// </summary>
	EC_DEVICE_NO_RESPOND, // 11
	/// <summary>
	/// Ошибка обмена данными с устройством
	/// </summary>
	EC_DEVICE_COMM_FAILURE, // 12
	/// <summary>
	/// Ошибка при обработке входящих сообщений протокола
	/// </summary>
	EC_DEVICE_PROTOCOL_FAILURE,  // 13
	/// <summary>
	/// Очередь событий пуста
	/// </summary>
	EC_POLL_NO_EVENTS, // 14
	/// <summary>
	/// Очередь закрыта или уничтожена
	/// </summary>
	EC_POLL_QUEUE_CLOSED, // 15
	// ошибки взаимодействия
	/// <summary>
	/// Устройству требуется инициализация
	/// </summary>
	EC_CALL_INIT, // 16

	/// <summary>
	/// Нет такой команды или команда не поддерживается устройством
	/// </summary>
	EC_DEVICE_INVALID_COMMAND, // 17

	/// <summary>
	/// Указан недопустимый параметр команды
	/// </summary>
	EC_DEVICE_INVALID_PARAM, // 18

	/// <summary>
	/// Неверный PIN для команд настройки
	/// </summary>
	EC_DEVICE_INVALID_PIN, // 19

	/// <summary>
	/// Истекло время ожидания на получение устройством нужной команды
	/// </summary>
	EC_DEVICE_COMMAND_TIMEOUT, // 20

	/// <summary>
	/// Нет карты на считывателе
	/// </summary>
	EC_DEVICE_NO_CARD, // 21

	/// <summary>
	/// Устройство не смогло распознать карту
	/// </summary>
	EC_DEVICE_UOWN_CARD, // 22

	/// <summary>
	/// Карта несовместима с выполняемой операцией
	/// </summary>
	EC_DEVICE_INCOMPATIBLE_CARD, // 23

	/// <summary>
	/// Авторизация карты не проходит
	/// </summary>
	EC_DEVICE_AUTH_FAIL,  // 24

	/// <summary>
	/// Используется неподходящий профиль
	/// </summary>
	EC_DEVICE_PROFILE_FAIL, // 25

	/// <summary>
	/// Авторизация карты на чтение/запись не проходит
	/// </summary>
	EC_DEVICE_RW_FAIL, // 26

	/// <summary>
	/// Ошибка при открытии соединения
	/// </summary>
	EC_IO_OPEN_FAIL, // 27

	/// <summary>
	/// Ошибка при закрытии соединения
	/// </summary>
	EC_IO_CLOSE_FAIL, // 28

	/// <summary>
	/// Ошибка при откправке данных
	/// </summary>
	EC_IO_READ_FAIL, // 29

	/// <summary>
	/// Ошибка при чтении данных
	/// </summary>
	EC_IO_WRITE_FAIL, // 30

	/// <summary>
	/// Операция прервана, соединение было закрыто
	/// </summary>
	EC_IO_CLOSED, // 31,

	/// <summary>
	/// Тестовая, пока не вызывается
	/// </summary>
	EC_DEVICE_IN_BOOT, // 32
	
	/// <summary>
	/// Файл прошивки не соответствует модели устройства
	/// </summary>
	EC_DEVICE_FW_INVALID_MODEL, // 33

	/// <summary>
	/// Файл не найден
	/// </summary>
	EC_FILE_NOT_FOUND, // 34

	EC_FINGERPRINT_UNFOUND, // 35

} E_API_ERROR_CODES;
