# Conan tools

- общий рецепт conanfile
- скрипты для использования Conan из IDE QtCreator

## Usage

Положить xml файлы в %APPDATA%\QtProject\qtcreator\externaltools
Перезапустить Qt Creator

Инструменты->Внешние->Conan->Выбирай что хочешь

## Особенности

- Важно, чтобы именование комплектов Qt было аналогично дефолтному "... Qt %{version} %{compilerName} ...". Для определения версии Qt тулзы ориентируются по имени комплекта

Примеры:

```text
Desktop Qt 5.5.1 MinGW 32-bit
Desktop Qt 5.15.2 MinGW 32-bit
Desktop Qt 5.15.2 MSVC2019 32-bit
```

- Из-за бага внутри QtCreator какая-то фигня с переменной типа сборки, когда релизная сборка, он пишет тип unknown
