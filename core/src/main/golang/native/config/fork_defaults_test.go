package config

import (
	"fmt"
	"testing"

	coreconfig "github.com/metacubex/mihomo/config"
	"github.com/metacubex/mihomo/constant"
)

func TestForkDefaultSettingsPreserveStoredChoices(t *testing.T) {
	home := constant.Path.HomeDir()
	session := sessionOverride
	t.Cleanup(func() {
		constant.SetHomeDir(home)
		sessionOverride = session
	})
	ClearOverride(OverrideSlotSession)
	if ReadOverride(OverrideSlotSession) != "{}" {
		t.Fatal("Session override must remain empty")
	}
	cases := []struct {
		name string
		content string
		write bool
		inherit bool
		value bool
	}{
		{name: "new", value: true},
		{name: "empty", content: "{}", write: true, inherit: true},
		{name: "null", content: `{"unified-delay":null,"tcp-concurrent":null}`, write: true, inherit: true},
		{name: "off", content: `{"unified-delay":false,"tcp-concurrent":false}`, write: true},
		{name: "on", content: `{"unified-delay":true,"tcp-concurrent":true}`, write: true, value: true},
	}
	for _, tc := range cases {
		for _, initial := range []bool{false, true} {
			t.Run(fmt.Sprintf("%s/profile-%t", tc.name, initial), func(t *testing.T) {
				constant.SetHomeDir(t.TempDir())
				if tc.write {
					WriteOverride(OverrideSlotPersist, tc.content)
					if got := ReadOverride(OverrideSlotPersist); got != tc.content {
						t.Fatalf("Stored override changed: %q", got)
					}
				}
				cfg := coreconfig.RawConfig{
					UnifiedDelay: initial,
					TCPConcurrent: initial,
					IPv6: !initial,
				}
				if err := patchOverride(&cfg, ""); err != nil {
					t.Fatal(err)
				}
				want := tc.value
				if tc.inherit {
					want = initial
				}
				if cfg.UnifiedDelay != want || cfg.TCPConcurrent != want {
					t.Fatalf("Meta defaults/choices differ: delay=%t, concurrent=%t, want=%t", cfg.UnifiedDelay, cfg.TCPConcurrent, want)
				}
				if cfg.IPv6 != !initial {
					t.Fatal("Kernel IPv6 must retain the profile value")
				}
			})
		}
	}
}
