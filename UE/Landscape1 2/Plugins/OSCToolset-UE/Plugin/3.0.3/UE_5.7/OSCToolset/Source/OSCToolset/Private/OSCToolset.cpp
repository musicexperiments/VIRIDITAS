// Copyright Epic Games, Inc. All Rights Reserved.

#include "OSCToolset.h"
#include "OSCToolsetLog.h"
#include "Modules/ModuleManager.h"
#include "Developer/Settings/Public/ISettingsModule.h"
#include "OSCT_Settings.h"

#define LOCTEXT_NAMESPACE "FOSCToolsetModule"
DEFINE_LOG_CATEGORY(OSCToolset);

void FOSCToolsetModule::StartupModule()
{
	// This code will execute after your module is loaded into memory; the exact timing is specified in the .uplugin file per-module
      // Register settings page
    if (ISettingsModule* SettingsModule = FModuleManager::GetModulePtr<ISettingsModule>("Settings"))
    {
        SettingsModule->RegisterSettings(
            "Project",                         // Category: Project Settings
            "Plugins",                         // Section: Plugins
            "OSCToolset",                      // Name: Your plugin's settings page
            LOCTEXT("OSCToolsetSettingsName", "OSCToolset"),  // Display Name
            LOCTEXT("OSCToolsetSettingsDesc", "Configure settings for OSC Toolset."),  // Description
            GetMutableDefault<UOSCT_Settings>()  // Reference to your settings object
        );
    }
}

void FOSCToolsetModule::ShutdownModule()
{
	// This function may be called during shutdown to clean up your module.  For modules that support dynamic reloading,
	// we call this function before unloading the module.
    // Unregister settings when shutting down
    if (ISettingsModule* SettingsModule = FModuleManager::GetModulePtr<ISettingsModule>("Settings"))
    {
        SettingsModule->UnregisterSettings("Project", "Plugins", "OSCToolset");
    }
}

#undef LOCTEXT_NAMESPACE
	
IMPLEMENT_MODULE(FOSCToolsetModule, OSCToolset)