APP := build/Agent Center.app

.PHONY: help build package run open install uninstall icon stop clean

help:
	@echo "make install    build and install to /Applications, then launch"
	@echo "make run        build and run in the foreground (logs to terminal)"
	@echo "make open       build and launch detached"
	@echo "make package    build the .app bundle only"
	@echo "make uninstall  quit and remove the installed app"
	@echo "make clean      remove build artefacts"

build:
	swift build -c release

package:
	./Scripts/package_app.sh release

icon:
	swift Scripts/make_icon.swift

run: package stop
	"$(APP)/Contents/MacOS/AgentCenter"

open: package stop
	open -n "$(APP)"

install: package stop
	rm -rf "/Applications/Agent Center.app"
	cp -R "$(APP)" /Applications/
	open "/Applications/Agent Center.app"
	@echo "installed — look for the bell in your menu bar"

uninstall: stop
	rm -rf "/Applications/Agent Center.app"
	@echo "removed. Credentials remain in the login keychain; delete the"
	@echo "'ai.tydra.agent-center' items in Keychain Access to clear them."

stop:
	@pkill -x AgentCenter 2>/dev/null || true

clean:
	rm -rf .build build
