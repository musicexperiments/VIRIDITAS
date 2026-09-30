// Copyright (c) 2024, Studio Eusebi Jucgla. All rights reserved 
// MD5: 2245b93ed1bae2e4aff277e6f3ecb8ff


#pragma once

#include "CoreMinimal.h"
#include "Subsystems/LocalPlayerSubsystem.h"
#include "Components/InputComponent.h"

#include "OSCT_LocalPlayer.generated.h"

/**
 * 
 */
UCLASS()
class OSCTOOLSET_API UOSCT_LocalPlayer : public ULocalPlayerSubsystem
{
	GENERATED_BODY()

public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

private:
    void BindShortcut();
    void ShowSettingsWidget();

    // Weak reference to InputComponent
    TWeakObjectPtr<UInputComponent> InputComponent;
    FTimerHandle BindShortcutTimerHandle;
};
