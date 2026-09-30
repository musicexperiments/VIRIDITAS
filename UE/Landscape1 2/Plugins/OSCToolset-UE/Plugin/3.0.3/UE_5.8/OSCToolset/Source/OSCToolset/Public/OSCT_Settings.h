// Copyright (c) 2024, Studio Eusebi Jucgla. All rights reserved.
// MD5: 2245b93ed1bae2e4aff277e6f3ecb8ff

#pragma once

#include "CoreMinimal.h"
#include "UObject/NoExportTypes.h"
#include "OSCT_Settings.generated.h"

/**
 * 
 */

USTRUCT(BlueprintType)
struct FOSCT_Network
{
	GENERATED_BODY()
	
	UPROPERTY(EditAnywhere, Category = "OSCToolset|Network")
	FString Address = TEXT("127.0.0.1");
	
	UPROPERTY(EditAnywhere, Category = "OSCToolset|Network")
	int32 Port = 9990;
};

UCLASS(config = User, defaultconfig)
class OSCTOOLSET_API UOSCT_Settings : public UObject
{
	GENERATED_BODY()

public:
    UOSCT_Settings();

	
	UPROPERTY(EditAnywhere, config, Category = "OSCToolset|Server (Receive)")
	FOSCT_Network ServerConfig;
	
	UPROPERTY(EditAnywhere, config, category = "OSCToolset|Server (Receive)")
	bool MulticastLoopback;
	
	UPROPERTY(EditAnywhere, config, Category = "OSCToolset|Clients (Send)")
	TArray<FOSCT_Network> RemoteClients;
	
	UPROPERTY(EditAnywhere, config, category = "OSCToolset")
	bool UseLocalIPV4;
};