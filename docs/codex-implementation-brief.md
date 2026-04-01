\# Codex Implementation Brief

\## DION ABA1



\## 1. Задача

Нужно реализовать офлайн-ПО для вендинг-аппарата DION ABA1 под Linux/Raspbian.



Система должна поддерживать:

\- авторизацию RFID/PIN;

\- выдачу;

\- возврат;

\- пополнение;

\- инвентаризацию;

\- локальную БД;

\- журналы и аудит;

\- экспорт CSV/XLSX;

\- сервисный режим;

\- recovery after crash;

\- интеграцию с барабаном, замками и RFID.



\## 2. Архитектурные правила



\### 2.1. Обязательное разделение слоев

Проект обязан быть разделен на слои:

\- `ui`

\- `application`

\- `domain` \*(если нужен отдельный уровень моделей и правил)\*

\- `infrastructure`

\- `hardware`

\- `persistence`

\- `reporting`

\- `tests`



\### 2.2. Что запрещено

Запрещено:

\- смешивать UI и работу с железом;

\- обращаться к барабану/замкам напрямую из UI;

\- писать raw SQL из экранов;

\- хранить бизнес-логику внутри адаптеров оборудования;

\- использовать event log как источник истины по остаткам;

\- списывать/увеличивать остатки до завершения подтвержденной операции;

\- автоматически считать спорную recovery-операцию успешной без доказательств.



\### 2.3. Источники истины

\- текущее состояние остатков: `inventory\_balances`

\- история движения остатков: `inventory\_transactions`

\- текущее состояние операции: `operations.operation\_state`

\- история состояния: `operation\_state\_history`



\## 3. Рекомендуемый стек



\### Базовый стек

\- Python 3.11+

\- PySide6 / Qt for UI

\- SQLAlchemy 2.x

\- SQLite для MVP локальной БД

\- Alembic для миграций

\- pydantic для DTO / settings / validation

\- openpyxl для XLSX

\- pytest для тестов



\### Логирование

\- стандартный `logging`

\- отдельные логгеры для:

&#x20; - app

&#x20; - hardware

&#x20; - recovery

&#x20; - audit/export



\## 4. Структура проекта



Рекомендуемая структура:



\- `app/main.py`

\- `app/bootstrap.py`

\- `app/config/`

\- `app/ui/`

\- `app/application/`

\- `app/domain/`

\- `app/persistence/`

\- `app/hardware/`

\- `app/reporting/`

\- `app/recovery/`

\- `app/services/`

\- `app/tests/`

\- `docs/`



Пример детализации:



\- `app/application/auth\_service.py`

\- `app/application/dispense\_service.py`

\- `app/application/return\_service.py`

\- `app/application/refill\_service.py`

\- `app/application/recovery\_service.py`

\- `app/hardware/drum\_adapter.py`

\- `app/hardware/lock\_adapter.py`

\- `app/hardware/rfid\_adapter.py`

\- `app/hardware/facade.py`

\- `app/persistence/models.py`

\- `app/persistence/session.py`

\- `app/persistence/repositories/`

\- `app/ui/screens/`



\## 5. Что генерировать в первую очередь



Порядок реализации:



\### Этап A

\- конфиг проекта;

\- SQLAlchemy models;

\- Alembic migrations;

\- базовый app bootstrap;

\- logging setup.



\### Этап B

\- domain enums / constants;

\- application DTOs;

\- repository layer.



\### Этап C

\- state-machine aware services:

&#x20; - auth

&#x20; - dispense

&#x20; - return

&#x20; - refill

&#x20; - recovery



\### Этап D

\- hardware adapters:

&#x20; - drum

&#x20; - lock

&#x20; - rfid

&#x20; - mock versions



\### Этап E

\- UI skeleton;

\- основные экраны;

\- wiring UI ↔ application.



\### Этап F

\- export/reporting;

\- backup/restore;

\- service mode.



\## 6. Требования к модели данных



Нужно реализовать модели минимум для таблиц:

\- roles

\- users

\- user\_credentials

\- user\_rfid\_cards

\- item\_groups

\- items

\- slots

\- slot\_item\_bindings

\- permissions

\- system\_settings

\- hardware\_endpoints

\- inventory\_balances

\- inventory\_transactions

\- operation\_sessions

\- operations

\- operation\_state\_history

\- event\_logs

\- audit\_logs

\- recovery\_cases

\- recovery\_case\_entities

\- recovery\_actions

\- manual\_resolution\_actions

\- exports

\- backups



\## 7. Требования к операциям



\### Выдача

Обязательно:

\- отдельная state machine;

\- остаток списывать только после `completion\_verification`;

\- хранить переходы состояния;

\- хранить hardware context.



\### Возврат

Обязательно:

\- отдельный этап выбора ячейки возврата;

\- остаток увеличивать только в конце;

\- не делать ложных утверждений о физически доказанном возврате без датчика.



\### Пополнение

Обязательно:

\- моделировать как session;

\- каждое изменение остатка по ячейке — отдельная атомарная операция `refill\_item` или эквивалент.



\### Recovery

Обязательно:

\- отдельный сервис;

\- отдельные recovery entities;

\- ручная разборка спорных случаев;

\- не изменять историю задним числом.



\## 8. Требования к hardware layer



\### Drum adapter

Должен:

\- скрывать байтовый протокол;

\- поддерживать `get\_position`, `move\_to\_position`, `ping`;

\- обрабатывать accepted/busy/result/ok/err;

\- обрабатывать timeouts;

\- сохранять raw frames.



\### Lock adapter

Должен:

\- работать по RS-485;

\- поддерживать `get\_lock\_status`, `unlock\_lock`, `get\_unlock\_time`, `set\_unlock\_time`, `get\_version`;

\- нормализовать ASK-коды;

\- не пускать broadcast в обычную пользовательскую логику.



\### RFID adapter

Должен:

\- поддерживать подключение R5-USB;

\- нормализовать UID;

\- подавлять повторные чтения в окне debounce;

\- уметь работать через mock driver.



\### HardwareFacade

Application-слой работает только через facade.



\## 9. Требования к тестированию



Нужно писать:

\- unit tests для business logic;

\- unit tests для state transitions;

\- unit tests для inventory transactions;

\- unit tests для recovery classification;

\- mock-based integration tests для hardware facade;

\- migration smoke tests.



Критические тесты:

\- выдача с успешным завершением;

\- выдача с таймаутом после открытия замка;

\- возврат со спорным завершением;

\- пополнение с падением между ячейками;

\- recovery после незавершенной выдачи;

\- recovery после незавершенного возврата;

\- recovery после частично завершенной refill session.



\## 10. Требования к коду



\### Стиль

\- маленькие классы и модули;

\- явные dataclasses / pydantic models для обмена данными;

\- enums для operation states, results, roles, transaction types;

\- без магических строк в бизнес-логике;

\- type hints обязательны.



\### Исключения

\- отдельные typed exceptions для:

&#x20; - hardware errors

&#x20; - validation errors

&#x20; - recovery errors

&#x20; - persistence errors



\### Логирование

Каждый критический переход должен логироваться.



\## 11. Что нужно реализовать сначала как mock



До подключения реального железа обязательно сделать mock/simulator для:

\- барабана;

\- замков;

\- RFID.



Mock должен уметь воспроизводить:

\- normal success flow;

\- busy;

\- timeout;

\- communication error;

\- failed result;

\- repeated card reads.



\## 12. Первые deliverables от Codex



Нужно сгенерировать по порядку:

1\. каркас проекта;

2\. SQLAlchemy models + enums;

3\. Alembic migrations;

4\. repository layer;

5\. skeleton services for dispense/return/refill/recovery;

6\. mock hardware adapters;

7\. basic CLI/dev harness для прогонки сценариев без UI;

8\. только после этого — UI skeleton.



\## 13. Чего Codex не должен делать



Codex не должен:

\- придумывать неописанные аппаратные команды;

\- упрощать recovery до “поставить failed всем незавершенным операциям”;

\- считать возврат физически подтвержденным без достаточных оснований;

\- зашивать protocol constants в UI;

\- смешивать business logic и SQL-модели в одну кучу.



\## 14. Definition of Done для первой рабочей версии



Первая рабочая версия считается готовой, если:

\- поднимается приложение и БД;

\- миграции применяются;

\- есть модели и репозитории;

\- есть mock hardware layer;

\- выдача/возврат/пополнение проходят через state machine;

\- inventory transactions пишутся корректно;

\- recovery умеет классифицировать незавершенные операции;

\- базовые тесты проходят.

