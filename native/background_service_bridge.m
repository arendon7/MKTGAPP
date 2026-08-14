#import <Foundation/Foundation.h>
#import <ServiceManagement/ServiceManagement.h>

static NSString *binario_status_name(SMAppServiceStatus status) API_AVAILABLE(macos(13.0)) {
    switch (status) {
        case SMAppServiceStatusNotRegistered:
            return @"not-registered";
        case SMAppServiceStatusEnabled:
            return @"enabled";
        case SMAppServiceStatusRequiresApproval:
            return @"requires-approval";
        case SMAppServiceStatusNotFound:
            return @"not-found";
    }
    return @"unknown";
}

static int binario_emit(NSDictionary *payload, int code) {
    NSError *error = nil;
    NSData *data = [NSJSONSerialization dataWithJSONObject:payload options:NSJSONWritingSortedKeys error:&error];
    if (data == nil || error != nil) {
        fputs("{\"error\":\"background service JSON failure\"}\n", stdout);
        return 3;
    }
    fwrite(data.bytes, 1, data.length, stdout);
    fputc('\n', stdout);
    fflush(stdout);
    return code;
}

int binario_background_service_command(const char *raw_command) {
    @autoreleasepool {
        NSString *command = raw_command ? [NSString stringWithUTF8String:raw_command] : @"status";
        if (@available(macOS 13.0, *)) {
            SMAppService *service = [SMAppService agentServiceWithPlistName:@"com.sistemabinario.marketing.background.plist"];
            NSError *error = nil;

            if ([command isEqualToString:@"register"]) {
                if (![service registerAndReturnError:&error]) {
                    return binario_emit(@{
                        @"supported": @YES,
                        @"status": binario_status_name(service.status),
                        @"requires_approval": @(service.status == SMAppServiceStatusRequiresApproval),
                        @"error": error.localizedDescription ?: @"background service registration failed"
                    }, 4);
                }
            } else if ([command isEqualToString:@"unregister"]) {
                if (![service unregisterAndReturnError:&error]) {
                    return binario_emit(@{
                        @"supported": @YES,
                        @"status": binario_status_name(service.status),
                        @"requires_approval": @(service.status == SMAppServiceStatusRequiresApproval),
                        @"error": error.localizedDescription ?: @"background service unregistration failed"
                    }, 4);
                }
            } else if ([command isEqualToString:@"open-settings"]) {
                [SMAppService openSystemSettingsLoginItems];
            } else if (![command isEqualToString:@"status"]) {
                return binario_emit(@{@"supported": @YES, @"error": @"unsupported command"}, 2);
            }

            NSMutableDictionary *payload = [@{
                @"supported": @YES,
                @"status": binario_status_name(service.status),
                @"requires_approval": @(service.status == SMAppServiceStatusRequiresApproval)
            } mutableCopy];
            if ([command isEqualToString:@"open-settings"]) payload[@"settings_opened"] = @YES;
            return binario_emit(payload, 0);
        }

        return binario_emit(@{
            @"supported": @NO,
            @"status": @"unsupported",
            @"requires_approval": @NO
        }, 0);
    }
}
