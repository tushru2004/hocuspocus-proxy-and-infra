# macOS VPN Profile Installation Issue

## Problem Summary

VPN profile installation fails on MacBook Air with "certificate cannot be verified" or "authentication error" when trying to install via:
1. SimpleMDM push (profiles never arrive)
2. Manual profile installation (authentication error)

## Device Details

- **Device:** MacBook Air (M2, 2023) - Mac14,15
- **macOS:** 26.2 (Build 25C56)
- **Serial:** KM2KW1KHWF
- **SimpleMDM ID:** 2162127
- **MDM Enrollment:** User-Approved (NOT DEP)
- **Supervised:** Yes (shows `IsSupervised = 1`)

## What Works

- SimpleMDM Agent is installed and running
- Device checks in with MDM successfully
- Existing profiles (SimpleMDM CA, SimpleMDM Agent) are installed via MDM
- VPN CA certificate is trusted in Keychain ("Always Trust")
- Client certificate (macbook-air) is imported to Keychain

## What Doesn't Work

### SimpleMDM Profile Push
- Profiles get uploaded and assigned to device
- Device shows as online (last_seen updates)
- But profiles never appear on device
- No errors in SimpleMDM logs
- Profile status shows yellow (pending) indefinitely

### Manual Profile Installation
Every profile type fails with authentication/verification errors:

1. **Full VPN profile** (CA + mitmproxy CA + client cert + VPN config)
   - Error: "Profile installation failed - authentication error"

2. **Certificate-only profile** (just PKCS12)
   - Error: "Certificate cannot be verified"

3. **VPN config only** (no certs, references existing cert)
   - Error: "The VPN service could not be created"

4. **Client cert + VPN config** (no root CA payload)
   - Error: "authentication error"

## Attempted Solutions

1. **Trusted CA in Keychain** - CA shows "Always Trust" but profiles still fail
2. **Imported client cert to Keychain** - Cert is in login keychain
3. **Different PKCS12 formats** - Tried with/without CA chain, different MAC algorithms
4. **SimpleMDM script approach** - Script API had issues
5. **Device restart** - No effect
6. **MDM check-in commands** - `sudo /usr/libexec/mdmclient QueryDeviceInformation` works but doesn't trigger profile install

## Technical Details

### VPN Configuration
- **Server IP:** 35.210.225.36
- **Protocol:** IKEv2
- **Auth:** Certificate-based
- **Local ID:** macbook-air
- **Expected IP:** 10.10.10.20

### Certificate Chain
```
CA: CN=Hocuspocus VPN CA (valid until 2036)
  └── Client: CN=macbook-air (valid until 2031)
```

### Profile Structure Tried
```xml
<!-- Full profile includes: -->
1. com.apple.security.root (VPN CA) - CAUSES ISSUES?
2. com.apple.security.root (mitmproxy CA) - CAUSES ISSUES?
3. com.apple.security.pkcs12 (client identity)
4. com.apple.vpn.managed (IKEv2 config)
```

## Possible Root Causes

1. **User-Approved MDM Limitations**
   - macOS with user-approved MDM (not DEP) has restrictions
   - Some profile types may require additional approval
   - APNs push notifications may not trigger profile installation

2. **Root CA Payload Rejection**
   - macOS may reject profiles containing `com.apple.security.root` payloads
   - Even when the same CA is already trusted in Keychain

3. **Certificate Verification**
   - The client certificate's issuer (VPN CA) may not be properly trusted for profile installation
   - Different trust settings needed for "Profile Signing" vs general SSL

4. **Profile Signing**
   - Profiles may need to be signed by a trusted certificate
   - SimpleMDM signs profiles but manual profiles are unsigned

## Workarounds to Try

1. **Manual VPN Configuration**
   - Skip profile, configure VPN manually in System Settings
   - Use certificate already in Keychain
   - Won't have "Always On" or MDM management

2. **DEP Enrollment**
   - Requires Apple Business Manager
   - Would give full MDM control
   - Requires device wipe

3. **Apple Configurator Profile Signing**
   - Sign profile with a trusted certificate
   - May bypass verification issues

4. **Different Certificate Format**
   - Try DER instead of PEM
   - Try different PKCS12 encryption algorithms

## Commands for Debugging

```bash
# Check installed profiles
sudo /usr/libexec/mdmclient QueryInstalledProfiles

# Force MDM check-in
sudo /usr/libexec/mdmclient QueryDeviceInformation

# Check MDM enrollment
profiles status -type enrollment

# List certificates in keychain
security find-certificate -a -c "Hocuspocus" /Library/Keychains/System.keychain

# Check certificate trust
security verify-cert -c /path/to/cert.pem
```

## Files

- VPN Profile: `vpn-profiles/hocuspocus-vpn-macbook-air.mobileconfig`
- VPN CA: `vpn-profiles/vpn-ca.pem` (also in MacBook Downloads)
- Client P12: `vpn-profiles/vpn-client.p12` (also in MacBook Downloads)

## Related

- iPhone profile installation works fine via SimpleMDM
- iPhone uses same CA and certificate structure
- Difference: iPhone is supervised via Apple Configurator (not user-approved MDM)
