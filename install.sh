#!/bin/sh
# Установщик Liquibase Forge в проект с SDD Developer Kit.
#
# Запускается из корня целевого проекта:
#   curl -fsSL https://raw.githubusercontent.com/united-software-platform/liquibase-forge/main/install.sh | sh
#   sh install.sh [--ref <тег> | --source <каталог>] [--dry-run] [--yes]
#
# Порядок: проверки, затем план без записи, затем подтверждение правок владельца, затем запись —
# файлы поставки, блоки в файлах kit'а, манифест .forge-manifest.json. Ошибка на любом шаге
# до записи не оставляет в проекте следов.
#
# Коды возврата: 0 — установка выполнена или менять нечего; 1 — не выполнено предусловие,
# версия не поддерживает установку, блок не вставлен или владелец отказался от перезаписи;
# 2 — ошибка вызова или окружения.
set -eu

REPOSITORY=united-software-platform/liquibase-forge
KIT_MANIFEST=.sdd-kit-manifest.json
KIT_MIN_VERSION=1.5.0
MANIFEST=.forge-manifest.json
MARK_BEGIN='# >>> liquibase-forge'
MARK_END='# <<< liquibase-forge'
TAB=$(printf '\t')

# Блоки в файлах kit'а: фрагмент install/blocks/, файл проекта, способ найти место вставки
BLOCKS='Makefile|Makefile|end
env.example|.env.example|end
docker-compose.yml|docker-compose.yml|compose
runner.py|tools/host-runner/runner.py|runner
gitignore|.gitignore|end'

usage() {
	cat <<'EOF'
Установка Liquibase Forge в проект с SDD Developer Kit (запуск из корня проекта).

  sh install.sh [--ref <тег> | --source <каталог>] [--dry-run] [--yes]

  --ref <тег>         версия forge — тег репозитория; по умолчанию последний релиз
  --source <каталог>  поставка из локальной копии репозитория forge
  --dry-run           напечатать план и ничего не записывать
  --yes               перезаписывать правки владельца без вопроса
EOF
}

fail_usage() {
	echo "Ошибка: $*" >&2
	exit 2
}

fail() {
	echo "Ошибка: $*" >&2
	exit 1
}

# --- Ключи -----------------------------------------------------------------------------------

ref=""
source_dir=""
dry_run=0
assume_yes=0
while [ $# -gt 0 ]; do
	case $1 in
	--ref)
		[ $# -ge 2 ] && [ -n "$2" ] || fail_usage "ключу --ref нужен тег"
		ref=$2
		shift 2
		;;
	--ref=*)
		ref=${1#--ref=}
		[ -n "$ref" ] || fail_usage "ключу --ref нужен тег"
		shift
		;;
	--source)
		[ $# -ge 2 ] && [ -n "$2" ] || fail_usage "ключу --source нужен каталог"
		source_dir=$2
		shift 2
		;;
	--source=*)
		source_dir=${1#--source=}
		[ -n "$source_dir" ] || fail_usage "ключу --source нужен каталог"
		shift
		;;
	--dry-run)
		dry_run=1
		shift
		;;
	--yes)
		assume_yes=1
		shift
		;;
	-h | --help)
		usage
		exit 0
		;;
	*)
		usage >&2
		fail_usage "неизвестный ключ $1"
		;;
	esac
done
[ -z "$ref" ] || [ -z "$source_dir" ] || fail_usage "ключи --ref и --source взаимоисключающие"

# --- Окружение -------------------------------------------------------------------------------

for tool in mktemp sed awk find cp; do
	command -v "$tool" >/dev/null 2>&1 || fail_usage "не найдена утилита $tool"
done
if command -v sha256sum >/dev/null 2>&1; then
	sha_tool="sha256sum"
elif command -v shasum >/dev/null 2>&1; then
	sha_tool="shasum -a 256"
else
	fail_usage "не найдена утилита sha256sum или shasum"
fi
if [ -z "$source_dir" ]; then
	for tool in curl tar; do
		command -v "$tool" >/dev/null 2>&1 || fail_usage "не найдена утилита $tool — она нужна для загрузки архива forge"
	done
fi

sha_of() {
	$sha_tool "$1" | awk '{ print $1 }'
}

# Сравнение версий вида X.Y.Z: истина, если первая не ниже второй
version_at_least() {
	awk -v have="$1" -v need="$2" 'BEGIN {
		split(have, h, "."); split(need, n, ".")
		for (i = 1; i <= 3; i++) {
			if (h[i] + 0 > n[i] + 0) exit 0
			if (h[i] + 0 < n[i] + 0) exit 1
		}
		exit 0
	}'
}

# --- Предусловие: SDD Developer Kit ----------------------------------------------------------

[ -f "$KIT_MANIFEST" ] ||
	fail "в $(pwd) нет $KIT_MANIFEST: forge ставится в проект с SDD Developer Kit $KIT_MIN_VERSION или новее; запустите установщик из корня такого проекта"
kit_version=$(sed -n 's/.*"kit_version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$KIT_MANIFEST" | head -n 1)
[ -n "$kit_version" ] || fail "в $KIT_MANIFEST нет kit_version: нужен SDD Developer Kit $KIT_MIN_VERSION или новее"
version_at_least "$kit_version" "$KIT_MIN_VERSION" ||
	fail "найден SDD Developer Kit $kit_version, нужен $KIT_MIN_VERSION или новее — сначала обновите kit"

# --- Источник поставки -----------------------------------------------------------------------

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
trap 'exit 2' INT TERM

if [ -n "$source_dir" ]; then
	[ -d "$source_dir" ] || fail_usage "каталог $source_dir не найден"
	src=$(cd "$source_dir" && pwd)
	forge_ref=local
else
	if [ -z "$ref" ]; then
		latest=$(curl -fsSL "https://api.github.com/repos/$REPOSITORY/releases/latest") ||
			fail_usage "не удалось узнать последний релиз forge: нет сети или релиз не опубликован; укажите версию ключом --ref"
		ref=$(printf '%s\n' "$latest" | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)
		[ -n "$ref" ] || fail_usage "у forge нет опубликованного релиза; укажите версию ключом --ref"
	fi
	curl -fsSL "https://codeload.github.com/$REPOSITORY/tar.gz/$ref" -o "$work/forge.tar.gz" ||
		fail_usage "не удалось загрузить архив forge $ref: нет сети или такой версии нет"
	mkdir "$work/source"
	tar -xzf "$work/forge.tar.gz" -C "$work/source" || fail_usage "архив forge $ref не распаковался"
	set -- "$work/source"/*
	src=$1
	forge_ref=$ref
fi

[ -f "$src/delivery.txt" ] && [ -d "$src/install/blocks" ] ||
	fail "версия forge ${ref:-из $src} не поддерживает установку: в ней нет delivery.txt"
# Номер версии — первая строка VERSION источника, строго МАЖОР.МИНОР.ПАТЧ
forge_version=$(head -n 1 "$src/VERSION" 2>/dev/null) || forge_version=""
printf '%s\n' "$forge_version" | grep -Eqx '[0-9]+\.[0-9]+\.[0-9]+' ||
	fail "поставка повреждена: в VERSION нет номера версии вида МАЖОР.МИНОР.ПАТЧ, прочитано «$forge_version»"

# --- Прежняя установка -----------------------------------------------------------------------

# Суммы из манифеста прежней установки: строки «сумма<TAB>путь» отдельно для файлов и блоков
: >"$work/old_files"
: >"$work/old_blocks"
if [ -f "$MANIFEST" ]; then
	awk -v dir="$work" '
		/"files"[[:space:]]*:/ { section = "files" }
		/"blocks"[[:space:]]*:/ { section = "blocks" }
		/"path"[[:space:]]*:/ && section != "" {
			path = $0; sub(/.*"path"[[:space:]]*:[[:space:]]*"/, "", path); sub(/".*/, "", path)
			sum = $0; sub(/.*"sha256"[[:space:]]*:[[:space:]]*"/, "", sum); sub(/".*/, "", sum)
			print sum "\t" path > (dir "/old_" section)
		}
	' "$MANIFEST"
fi

old_sum() {
	awk -F "$TAB" -v path="$2" '$2 == path { print $1; exit }' "$work/old_$1"
}

# --- План: файлы поставки --------------------------------------------------------------------

# Строки «источник<TAB>цель» по каждому файлу: каталог перечня раскрывается рекурсивно,
# кеш байткода Python в поставку не входит
: >"$work/files"
while IFS= read -r line || [ -n "$line" ]; do
	case $line in '' | '#'*) continue ;; esac
	case $line in
	*' -> '*)
		from=${line%% -> *}
		to=${line#* -> }
		;;
	*)
		from=$line
		to=$line
		;;
	esac
	if [ -f "$src/$from" ]; then
		printf '%s\t%s\n' "$from" "$to" >>"$work/files"
	elif [ -d "$src/$from" ]; then
		(cd "$src" && find "$from" -name __pycache__ -prune -o -type f ! -name '*.pyc' -print) | sort |
			while IFS= read -r file; do
				printf '%s\t%s\n' "$file" "$to${file#"$from"}" >>"$work/files"
			done
	else
		fail "поставка повреждена: в delivery.txt есть $from, а в источнике его нет"
	fi
done <"$src/delivery.txt"

# Строки плана: «статус<TAB>вид<TAB>путь»; статусы create, update, same, owner, dropped
: >"$work/plan"
: >"$work/new_files"
while IFS="$TAB" read -r from to; do
	new_sum=$(sha_of "$src/$from")
	printf '%s\t%s\n' "$new_sum" "$to" >>"$work/new_files"
	if [ ! -f "$to" ]; then
		status=create
	else
		current=$(sha_of "$to")
		if [ "$current" = "$new_sum" ]; then
			status=same
		elif [ "$current" = "$(old_sum files "$to")" ]; then
			status=update
		else
			status=owner
		fi
	fi
	printf '%s\tfile\t%s\n' "$status" "$to" >>"$work/plan"
done <"$work/files"

awk -F "$TAB" 'NR == FNR { delivered[$2] = 1; next } !($2 in delivered) { print "dropped\tfile\t" $2 }' \
	"$work/new_files" "$work/old_files" >>"$work/plan"

# --- План: блоки в файлах kit'а --------------------------------------------------------------

# Положение маркеров: «начал концов строка_начала строка_конца»
markers_of() {
	awk -v b="$MARK_BEGIN" -v e="$MARK_END" '
		{ s = $0; sub(/^[ \t]+/, "", s); sub(/[ \t]+$/, "", s) }
		s == b { nb++; if (!lb) lb = NR }
		s == e { ne++; if (!le) le = NR }
		END { print nb + 0, ne + 0, lb + 0, le + 0 }
	' "$1"
}

# Вставка блока туда, где его нет; код 3 — место вставки не распознано
insert_block() {
	place=$1 target=$2 fragment=$3 indent=$4 out=$5
	case $place in
	end)
		[ -f "$target" ] && cat "$target" >"$out" || : >"$out"
		if [ -s "$out" ]; then
			[ -z "$(tail -c 1 "$out")" ] || printf '\n' >>"$out"
			[ -z "$(tail -n 1 "$out")" ] || printf '\n' >>"$out"
		fi
		{
			printf '%s%s\n' "$indent" "$MARK_BEGIN"
			cat "$fragment"
			printf '%s%s\n' "$indent" "$MARK_END"
		} >>"$out"
		;;
	compose)
		[ -f "$target" ] || return 3
		if grep -q '^include:' "$target"; then
			grep -Eq '^include:[[:space:]]*(#.*)?$' "$target" || return 3
			mode=after-include
		elif grep -Eq '^services:[[:space:]]*(#.*)?$' "$target"; then
			mode=before-services
		else
			return 3
		fi
		awk -v mode="$mode" -v fragment="$fragment" -v b="$indent$MARK_BEGIN" -v e="$indent$MARK_END" '
			function emit(  l) { print b; while ((getline l < fragment) > 0) print l; close(fragment); print e }
			!done && mode == "after-include" && /^include:/ { print; emit(); done = 1; next }
			!done && mode == "before-services" && /^services:/ { print "include:"; emit(); print ""; print; done = 1; next }
			{ print }
		' "$target" >"$out"
		;;
	runner)
		[ -f "$target" ] || return 3
		awk -v fragment="$fragment" -v b="$indent$MARK_BEGIN" -v e="$indent$MARK_END" '
			function emit(  l) { print b; while ((getline l < fragment) > 0) print l; close(fragment); print e }
			state == 0 && /^ALLOWED_TARGETS = frozenset\(/ { state = 1; print; next }
			state == 1 {
				s = $0; sub(/^[ \t]+/, "", s)
				if (s ~ /^}/) {
					# Без запятой после последнего элемента вставка склеила бы строки литерала
					if (previous !~ /[,{][ \t]*$/) { failed = 1; exit }
					emit(); state = 2; print; next
				}
				if (s != "" && s !~ /^#/) previous = s
			}
			{ print }
			END { if (failed || state != 2) exit 3 }
		' "$target" >"$out" || return 3
		;;
	esac
}

refuse_block() {
	echo "Ошибка: в $1 не найдено место вставки блока forge — файл не изменён, установка не выполнена." >&2
	echo "Вставьте блок вручную и запустите установщик повторно:" >&2
	printf '%s%s\n' "$3" "$MARK_BEGIN"
	cat "$2"
	printf '%s%s\n' "$3" "$MARK_END"
	exit 1
}

mkdir "$work/blocks"
: >"$work/new_blocks"
: >"$work/hints"
while IFS='|' read -r name target place; do
	fragment="$src/install/blocks/$name"
	[ -f "$fragment" ] || fail "поставка повреждена: нет фрагмента install/blocks/$name"
	indent=$(sed -n '1s/^\([[:space:]]*\).*/\1/p' "$fragment")
	out="$work/blocks/$name"
	new_sum=$(sha_of "$fragment")
	printf '%s\t%s\n' "$new_sum" "$target" >>"$work/new_blocks"

	if [ -f "$target" ]; then
		set -- $(markers_of "$target")
	else
		set -- 0 0 0 0
	fi
	if [ "$1" -eq 0 ] && [ "$2" -eq 0 ]; then
		[ -f "$target" ] || [ "$place" = end ] || refuse_block "$target" "$fragment" "$indent"
		insert_block "$place" "$target" "$fragment" "$indent" "$out" || refuse_block "$target" "$fragment" "$indent"
		status=create
		# Отличия forge, внесённые прежде без маркеров, после вставки задвоились бы
		if [ -f "$target" ]; then
			grep -v '^[[:space:]]*$' "$fragment" | grep -v '^[[:space:]]*#' | while IFS= read -r line; do
				grep -Fxq -- "$line" "$target" && printf '%s\n' "$target" >>"$work/hints"
			done || :
		fi
	elif [ "$1" -eq 1 ] && [ "$2" -eq 1 ] && [ "$3" -lt "$4" ]; then
		awk -v lb="$3" -v le="$4" 'NR > lb && NR < le' "$target" >"$work/current_block"
		current=$(sha_of "$work/current_block")
		{
			head -n "$3" "$target"
			cat "$fragment"
			tail -n "+$4" "$target"
		} >"$out"
		if [ "$current" = "$new_sum" ]; then
			status=same
		elif [ "$current" = "$(old_sum blocks "$target")" ]; then
			status=update
		else
			status=owner
		fi
	else
		refuse_block "$target" "$fragment" "$indent"
	fi
	printf '%s\tblock\t%s\n' "$status" "$target" >>"$work/plan"
done <<EOF
$BLOCKS
EOF

# --- Манифест --------------------------------------------------------------------------------

entries() {
	sort -t "$TAB" -k 2 "$1" | awk -F "$TAB" '
		{ line[NR] = "    {\"path\": \"" $2 "\", \"sha256\": \"" $1 "\"}" }
		END { for (i = 1; i <= NR; i++) print line[i] (i < NR ? "," : "") }
	'
}

{
	printf '{\n'
	printf '  "forge_version": "%s",\n' "$forge_version"
	printf '  "forge_ref": "%s",\n' "$forge_ref"
	printf '  "installed_at": "%s",\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
	printf '  "files": [\n'
	entries "$work/new_files"
	printf '  ],\n'
	printf '  "blocks": [\n'
	entries "$work/new_blocks"
	printf '  ]\n'
	printf '}\n'
} >"$work/manifest"

# --- Печать плана ----------------------------------------------------------------------------

count() {
	awk -F "$TAB" -v s="$1" '$1 == s { n++ } END { print n + 0 }' "$work/plan"
}

changes=$(($(count create) + $(count update) + $(count owner)))
owner_edits=$(count owner)
manifest_changed=1
if [ -f "$MANIFEST" ] &&
	grep -v '"installed_at"' "$MANIFEST" >"$work/old_manifest_body" &&
	grep -v '"installed_at"' "$work/manifest" | cmp -s - "$work/old_manifest_body"; then
	manifest_changed=0
fi

if [ "$forge_ref" = local ]; then
	echo "Liquibase Forge $forge_version из локальной копии $src"
else
	echo "Liquibase Forge $forge_version, версия $forge_ref"
fi
echo "План установки в $(pwd):"
awk -F "$TAB" '
	BEGIN {
		label["create"] = "создать"; label["update"] = "обновить"; label["same"] = "без изменений"
		label["owner"] = "правка владельца, перезаписать"; label["dropped"] = "больше не поставляется, не удаляется"
		kind["file"] = "файл"; kind["block"] = "блок forge в"
	}
	{ print "  " label[$1] ": " kind[$2] " " $3 }
' "$work/plan"
if [ -s "$work/hints" ]; then
	echo ""
	echo "Внимание: строки блока forge уже есть вне маркеров — после установки удалите прежние"
	echo "отличия forge вручную, иначе они задвоятся:"
	sort -u "$work/hints" | sed 's/^/  /'
fi
echo ""

if [ "$changes" -eq 0 ] && [ "$manifest_changed" -eq 0 ]; then
	echo "Менять нечего: установлена та же версия forge, правок нет."
	exit 0
fi
if [ "$dry_run" -eq 1 ]; then
	echo "Пробный запуск: ничего не записано."
	exit 0
fi

# --- Подтверждение ---------------------------------------------------------------------------

if [ "$owner_edits" -gt 0 ] && [ "$assume_yes" -eq 0 ]; then
	# Ответ читается из терминала, а не из stdin: при запуске через curl | sh stdin — сам скрипт
	answer=$(
		{
			printf 'Перезаписать правки владельца (%s)? [y/N] ' "$owner_edits" >/dev/tty &&
				read -r reply </dev/tty && printf '%s' "$reply"
		} 2>/dev/null
	) || {
		echo "Ошибка: правки владельца требуют подтверждения, а терминала нет — запустите с --yes" >&2
		exit 1
	}
	case $answer in
	y | Y | yes | YES | д | Д | да | ДА) ;;
	*)
		echo "Отказ от перезаписи: ничего не записано." >&2
		exit 1
		;;
	esac
fi

# --- Запись ----------------------------------------------------------------------------------

while IFS="$TAB" read -r from to; do
	status=$(awk -F "$TAB" -v path="$to" '$2 == "file" && $3 == path { print $1; exit }' "$work/plan")
	[ "$status" = same ] && continue
	mkdir -p "$(dirname "$to")"
	cp "$src/$from" "$to"
done <"$work/files"

while IFS='|' read -r name target place; do
	status=$(awk -F "$TAB" -v path="$target" '$2 == "block" && $3 == path { print $1; exit }' "$work/plan")
	[ "$status" = same ] && continue
	# cat, а не cp: файл kit'а сохраняет свои права, например исполняемый runner.py
	cat "$work/blocks/$name" >"$target"
done <<EOF
$BLOCKS
EOF

cp "$work/manifest" "$MANIFEST"

if [ "$changes" -eq 0 ]; then
	echo "Файлы поставки и блоки не изменились, обновлён $MANIFEST."
	exit 0
fi
echo "Liquibase Forge $forge_version установлен. Закоммитьте поставку вместе с $MANIFEST."
echo ""
echo "Следующие шаги:"
echo "  1. Перезапустите раннер на хосте: белый список целей читается при старте."
echo "  2. Попросите агента выполнить make forge-env-sync — дописать переменные forge в .env."
echo "  3. Попросите агента выполнить make forge-env-check — проверить Compose и состав сервисов."
