// Copyright (c) 2024, Studio Eusebi Jucgla. All rights reserved 
// MD5: 2245b93ed1bae2e4aff277e6f3ecb8ff

#include "UI/OSCT_LocalPlayer.h"

#include "Components/InputComponent.h"

#include "Kismet/GameplayStatics.h"

#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Engine/GameViewportClient.h"
#include "Engine/GameInstance.h"

#include "TimerManager.h"

#include "GameFramework/PlayerController.h"
#include "Engine/LocalPlayer.h"

#include "OSCT_Master.h"
#include "OSCToolsetLog.h"

void UOSCT_LocalPlayer::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);

    // Start a timer to periodically try to bind the shortcut
    GetWorld()->GetTimerManager().SetTimer(BindShortcutTimerHandle, this, &UOSCT_LocalPlayer::BindShortcut, 0.1f, true);
}

void UOSCT_LocalPlayer::Deinitialize()
{
    Super::Deinitialize();
}

void UOSCT_LocalPlayer::BindShortcut()
{
    // Ensure we have access to the LocalPlayer
    if (ULocalPlayer* LocalPlayer = GetLocalPlayer())
    {
        // Get the PlayerController from the LocalPlayer
        APlayerController* PlayerController = LocalPlayer->GetPlayerController(GetWorld());
        if (PlayerController)
        {
            InputComponent = PlayerController->InputComponent;

            if (InputComponent.IsValid())
            {
                // Bind CTRL+SHIFT+O to open the settings menu
                InputComponent->BindKey(FInputChord(EKeys::O, EModifierKey::Control | EModifierKey::Shift), IE_Pressed, this, &UOSCT_LocalPlayer::ShowSettingsWidget);
                UE_LOG(OSCToolset, Log, TEXT("Bind OSCT Settings Shortcut."));
                GetWorld()->GetTimerManager().ClearTimer(BindShortcutTimerHandle);
            }
            else {
                UE_LOG(OSCToolset, Error, TEXT("InputComponent is not valid."));
            }
        }
        else {
            UE_LOG(OSCToolset, Error, TEXT("Player Controller could not be found."));
        }
    }
}
    
void UOSCT_LocalPlayer::ShowSettingsWidget()
{
    if (GEngine && GEngine->GameViewport)
    {

        UOSCT_Master* OSCT_Master = GetWorld()->GetGameInstance()->GetSubsystem<UOSCT_Master>();
        if (OSCT_Master)
        {
            OSCT_Master->ToggleOSCTMenu();
        }
        UE_LOG(OSCToolset, Log, TEXT("Show OSCT Settings Widget."));
        //TSharedRef<SWidget> SettingsWidget = SNew(SSettingsWidget);
        //GEngine->GameViewport->AddViewportWidgetContent(SettingsWidget);
    }
}
