// Copyright (c) 2024, Studio Eusebi Jucgla. All rights reserved.
// MD5: 2245b93ed1bae2e4aff277e6f3ecb8ff

#include "OSCT_Settings.h"

UOSCT_Settings::UOSCT_Settings()
{
	ServerConfig.Address = TEXT("0.0.0.0");
	ServerConfig.Port = 9999;

	FOSCT_Network DefaultClient;
	DefaultClient.Address = TEXT("127.0.0.1");
	DefaultClient.Port = 9998;
    
	RemoteClients.Add(DefaultClient);
	
	MulticastLoopback = false;
	UseLocalIPV4 = false;
}
