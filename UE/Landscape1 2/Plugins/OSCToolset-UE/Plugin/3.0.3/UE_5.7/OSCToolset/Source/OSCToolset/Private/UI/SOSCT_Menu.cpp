// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/SOSCT_Menu.h"
#include "OSCT_Settings.h"
#include "OSCT_Master.h"

#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SCheckBox.h"

#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SBorder.h"

#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h" // Required for GameViewport.

#include "GameFramework/PlayerController.h"
#include "UObject/UnrealType.h"

// void SOSCT_Menu::Construct(const FArguments& InArgs)
// {
//     // Point to the actual config object
//     Settings = GetMutableDefault<UOSCT_Settings>();
//
//     if (GEngine && GEngine->GameViewport)
//     {
//         const int32 ui_padding = 5;
//         FVector2D ViewportSize;
//         GEngine->GameViewport->GetViewportSize(ViewportSize);
//         // Calculate one-third of the screen width
//         const float WidgetWidth = ViewportSize.X / 3.0f;
//
//         ChildSlot
//             [
//                 SNew(SOverlay)
//                     + SOverlay::Slot()
//                     .HAlign(HAlign_Left)
//                     [
//                         SNew(SBox)
//                             .WidthOverride(WidgetWidth)
//                             .HeightOverride(400)
//                             .Padding(150)
//                             [
//                                 SNew(SVerticalBox)
//                                     +SVerticalBox::Slot()
//                                     .AutoHeight()
//                                     .Padding(ui_padding)
//                                     [
//                                         SNew(STextBlock)
//                                             .Text(FText::FromString("OSCToolset Settings"))
//                                             .Font(FSlateFontInfo(FCoreStyle::GetDefaultFontStyle("Bold", 24)))
//                                     ]
//                                     + SVerticalBox::Slot()
//                                     .AutoHeight()
//                                     .Padding(FMargin(ui_padding, ui_padding, ui_padding, 50))
//                                     [
//                                         SNew(STextBlock)
//                                             .Text(FText::FromString("made by Eusebi Jucgla"))
//                                             .Font(FSlateFontInfo(FCoreStyle::GetDefaultFontStyle("Regular", 9)))
//                                     ]
//                                     + SVerticalBox::Slot()
//                                     .AutoHeight()
//                                     .Padding(ui_padding)
//                                     [
//                                         SNew(STextBlock)
//                                             .Text(FText::FromString("Server Address"))
//                                     ]
//                                     + SVerticalBox::Slot()
//                                     .AutoHeight()
//                                     .Padding(ui_padding)
//                                     [
//                                         SAssignNew(ServerAddressTextBox, SEditableTextBox)
//                                             .Text(FText::FromString(Settings->ServerConfig.Address))
//                                     ]
//                                     + SVerticalBox::Slot()
//                                     .AutoHeight()
//                                     .Padding(ui_padding)
//                                     [
//                                         SNew(STextBlock)
//                                             .Text(FText::FromString("Server Port"))
//                                     ]
//                                     + SVerticalBox::Slot()
//                                     .AutoHeight()
//                                     .Padding(ui_padding)
//                                     [
//                                         SAssignNew(ServerPortSpinBox, SSpinBox<int32>)
//                                             .Value(Settings->ServerConfig.Port)
//                                             .MinValue(1)
//                                             .MaxValue(65535)
//                                             .OnValueChanged_Lambda([this](int32 NewValue) {Settings->ServerConfig.Port = NewValue; })
//                                     ]
//                                     + SVerticalBox::Slot()
//                                     .AutoHeight()
//                                     .Padding(ui_padding)
//                                     [
//                                         SNew(STextBlock)
//                                             .Text(FText::FromString("Multicast Loopback"))
//                                     ]
//                                     + SVerticalBox::Slot()
//                                     .AutoHeight()
//                                     .Padding(ui_padding)
//                                     [
//                                         SAssignNew(MulticastLoopbackBox, SCheckBox)
//                                             .OnCheckStateChanged_Lambda([this](ECheckBoxState NewState)
//                                                 {
//                                                     Settings->MulticastLoopback = (NewState == ECheckBoxState::Checked);
//                                                 })
//                                             .IsChecked_Lambda([this]() -> ECheckBoxState
//                                                 {
//                                                     return Settings->MulticastLoopback ? ECheckBoxState::Checked : ECheckBoxState::Unchecked;
//                                                 })
//                                     ]
//                                     + SVerticalBox::Slot()
//                                     .AutoHeight()
//                                     .Padding(ui_padding)
//                                     [
//                                         SNew(SBox)
//                                             .HeightOverride(35) // Adjust thickness
//                                     ]
//                                 
//                                     // + SVerticalBox::Slot()
//                                     // .AutoHeight()
//                                     // .Padding(ui_padding)
//                                     // [
//                                     //     SNew(STextBlock)
//                                     //         .Text(FText::FromString("Client Address"))
//                                     // ]
//                                     // + SVerticalBox::Slot()
//                                     // .AutoHeight()
//                                     // .Padding(ui_padding)
//                                     // [
//                                     //     SAssignNew(ClientAddressTextBox, SEditableTextBox)
//                                     //         .Text(FText::FromString(ClientAddress))
//                                     // ]
//                                     // + SVerticalBox::Slot()
//                                     // .AutoHeight()
//                                     // .Padding(ui_padding)
//                                     // [
//                                     //     SNew(STextBlock)
//                                     //         .Text(FText::FromString("Client Port"))
//                                     // ]
//                                     // + SVerticalBox::Slot()
//                                     // .AutoHeight()
//                                     // .Padding(ui_padding)
//                                     // [
//                                     //     SAssignNew(ClientPortSpinBox, SSpinBox<int32>)
//                                     //         .Value(ClientPort)
//                                     //         .MinValue(1)
//                                     //         .MaxValue(65535)
//                                     //         .OnValueChanged_Lambda([this](int32 NewValue) {ClientPort = NewValue; })
//                                     // ]
//                                     + SVerticalBox::Slot()
//                                     .AutoHeight()
//                                     .Padding(ui_padding)
//                                     [
//                                         SNew(STextBlock)
//                                             .Text(FText::FromString("Use Local IPV4"))
//                                     ]
//                                     + SVerticalBox::Slot()
//                                     .AutoHeight()
//                                     .Padding(ui_padding)
//                                     [
//                                         SAssignNew(UseLocalIPV4Box, SCheckBox)
//                                             .OnCheckStateChanged_Lambda([this](ECheckBoxState NewState)
//                                                 {
//                                                     Settings->UseLocalIPV4 = (NewState == ECheckBoxState::Checked);
//                                                 })
//                                             .IsChecked_Lambda([this]() -> ECheckBoxState
//                                                 {
//                                                     return Settings->UseLocalIPV4 ? ECheckBoxState::Checked : ECheckBoxState::Unchecked;
//                                                 })
//                                     ]
//                                     + SVerticalBox::Slot()
//                                     .AutoHeight()
//                                     .Padding(FMargin(ui_padding, 25, ui_padding, ui_padding))
//                                     .HAlign(HAlign_Fill)
//                                     [
//                                         SNew(SButton)
//                                             .Text(FText::FromString("Save and Re-Initialize OSCToolset"))
//                                             .OnClicked(this, &SOSCT_Menu::OnReinitializeOSCT)
//                                             .HAlign(HAlign_Fill)
//                                     ]
//                             ]
//                     ]
//             ];
//     }
// }

void SOSCT_Menu::Construct(const FArguments& InArgs)
{
    Settings = GetMutableDefault<UOSCT_Settings>();
    const float ui_padding = 5.0f;
    
    ChildSlot
    [
        SNew(SOverlay)
        + SOverlay::Slot()
        .HAlign(HAlign_Left)
        [
            SNew(SBox)
            .WidthOverride(500) // Fixed width is usually safer for settings panels
            .Padding(20)
            [
                SAssignNew(MainContentBox, SVerticalBox)
                
                //  HEADER SECTION
                + SVerticalBox::Slot().AutoHeight().Padding(ui_padding)
                [ MakeHeaderWidget() ]

                // SERVER SETTINGS 
                + SVerticalBox::Slot().AutoHeight().Padding(ui_padding)
                [ MakeServerSettingsWidget() ]

                // CLIENT LIST
                + SVerticalBox::Slot().AutoHeight().Padding(ui_padding)
                [ SAssignNew(ClientListBox, SVerticalBox) ]

                // Local IPV4 Toggle
                + SVerticalBox::Slot().AutoHeight().Padding(ui_padding)
                [
                    SNew(SHorizontalBox)
                    + SHorizontalBox::Slot().AutoWidth()
                    [
                        SNew(SCheckBox)
                        .IsChecked_Lambda([this]() { return Settings->UseLocalIPV4 ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; })
                        .OnCheckStateChanged_Lambda([this](ECheckBoxState NewState) {
                            Settings->UseLocalIPV4 = (NewState == ECheckBoxState::Checked);
                        })
                    ]
                    + SHorizontalBox::Slot().AutoWidth().Padding(5, 0)
                    [ SNew(STextBlock).Text(FText::FromString("Use Local IPV4")).Font(LabelFont) ]
                ]
                
                // --- FOOTER / SAVE ---
                + SVerticalBox::Slot().AutoHeight().Padding(FMargin(ui_padding, 20))
                [
                    SNew(SButton)
                    .ContentPadding(FMargin(10, 5))
                    .OnClicked(this, &SOSCT_Menu::OnReinitializeOSCT)
                    [
                        SNew(STextBlock)
                        .Text(FText::FromString("Save and Re-Initialize OSCToolset"))
                        .Justification(ETextJustify::Center)
                    ]
                ]
            ]
        ]
    ];

    RefreshClientList();
}

void SOSCT_Menu::SaveSettings()
{
    if ( Settings)
    {
        Settings->SaveConfig();
    }
}

TSharedRef<SWidget> SOSCT_Menu::MakeHeaderWidget()
{
    return SNew(SVerticalBox)
        + SVerticalBox::Slot().AutoHeight()
        [
            SNew(STextBlock)
            .Text(FText::FromString("OSCToolset Settings"))
            .Font(FSlateFontInfo(FCoreStyle::GetDefaultFontStyle("Bold", 32)))
        ]
        + SVerticalBox::Slot().AutoHeight().Padding(0, 5, 0, 20)
        [
            SNew(STextBlock)
            .Text(FText::FromString("made by Eusebi Jucgla"))
            .Font(LabelFont)
        ];
}

TSharedRef<SWidget> SOSCT_Menu::MakeServerSettingsWidget()
{
    const float ui_padding = 5.0f;

    return SNew(SVerticalBox)
        // Server Address
        + SVerticalBox::Slot().AutoHeight().Padding(ui_padding)
        [ SNew(STextBlock).Text(FText::FromString("Server Address")).Font(TitleFont) ]
        + SVerticalBox::Slot().AutoHeight().Padding(ui_padding)
        [
            SNew(SEditableTextBox)
            .Font(LabelFont)
            .Text_Lambda([this]() { return FText::FromString(Settings->ServerConfig.Address); })
            .OnTextCommitted_Lambda([this](const FText& InText, ETextCommit::Type) {
                Settings->ServerConfig.Address = InText.ToString();
            })
        ]
        // Server Port
        + SVerticalBox::Slot().AutoHeight().Padding(ui_padding)
        [
            SNew(SSpinBox<int32>)
            .Font(LabelFont)
            .Value_Lambda([this]() { return Settings->ServerConfig.Port; })
            .MinValue(1).MaxValue(65535)
            .OnValueChanged_Lambda([this](int32 NewValue) {
                Settings->ServerConfig.Port = NewValue;
            })
        ]

        // Multicast Loopback
        + SVerticalBox::Slot().AutoHeight().Padding(ui_padding)
        [
            SNew(SHorizontalBox)
            + SHorizontalBox::Slot().AutoWidth()
            [
                SNew(SCheckBox)
                .IsChecked_Lambda([this]() { return Settings->MulticastLoopback ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; })
                .OnCheckStateChanged_Lambda([this](ECheckBoxState NewState) {
                    Settings->MulticastLoopback = (NewState == ECheckBoxState::Checked);
                })
            ]
            + SHorizontalBox::Slot().AutoWidth().Padding(5, 0)
            [ SNew(STextBlock).Text(FText::FromString("Multicast Loopback")).Font(LabelFont) ]
        ];

        // // Local IPV4 Toggle
        // + SVerticalBox::Slot().AutoHeight().Padding(ui_padding)
        // [
        //     SNew(SHorizontalBox)
        //     + SHorizontalBox::Slot().AutoWidth()
        //     [
        //         SNew(SCheckBox)
        //         .IsChecked_Lambda([this]() { return Settings->UseLocalIPV4 ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; })
        //         .OnCheckStateChanged_Lambda([this](ECheckBoxState NewState) {
        //             Settings->UseLocalIPV4 = (NewState == ECheckBoxState::Checked);
        //         })
        //     ]
        //     + SHorizontalBox::Slot().AutoWidth().Padding(5, 0)
        //     [ SNew(STextBlock).Text(FText::FromString("Use Local IPV4")).Font(LabelFont) ]
        // ];
}

void SOSCT_Menu::RefreshClientList()
{
    if (!ClientListBox.IsValid()) return;

    ClientListBox->ClearChildren();

    for (int32 i = 0; i < Settings->RemoteClients.Num(); ++i)
    {
        ClientListBox->AddSlot()
        .AutoHeight()
        .Padding(0, 10)
        [
            SNew(SVerticalBox)
            + SVerticalBox::Slot().AutoHeight()
            [
                SNew(STextBlock).Text(FText::Format(FText::FromString("Client {0} Address"), FText::AsNumber(i))).Font(TitleFont)
            ]
            + SVerticalBox::Slot().AutoHeight()
            [
                SNew(SEditableTextBox)
                .Font(LabelFont)
                .Text_Lambda([this, i]() { return FText::FromString(Settings->RemoteClients[i].Address); })
                .OnTextCommitted_Lambda([this, i](const FText& InText, ETextCommit::Type) {
                    Settings->RemoteClients[i].Address = InText.ToString();
                })
            ]
            + SVerticalBox::Slot().AutoHeight().Padding(2)
            [
                SNew(SSpinBox<int32>)
                    .Font(LabelFont)
                    .Value(Settings->RemoteClients[i].Port)
                    .OnValueChanged_Lambda([this, i](int32 NewValue) {
                        Settings->RemoteClients[i].Port = NewValue;
                    })
            ]
        ];
    }
}


FReply SOSCT_Menu::OnReinitializeOSCT()
{
    SaveSettings();
    OnReInitOSCT.ExecuteIfBound();
    return FReply::Handled();
}