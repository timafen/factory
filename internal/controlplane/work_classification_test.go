package controlplane

import "testing"

func TestTasksWorkClassUsesAutomationFacts(t *testing.T) {
	tests := []struct {
		name  string
		facts workClassificationFacts
		want  workClass
	}{
		{"factory patrol", workClassificationFacts{title: "ordinary task", scheduled: true, automationName: "Nightly", automationText: "factory pipeline patrol"}, workClassPatrol},
		{"task title does not classify", workClassificationFacts{title: "Patrol this", scheduled: false}, workClassProduct},
		{"ordinary schedule", workClassificationFacts{scheduled: true, automationName: "Nightly", automationText: "backup"}, workClassScheduled},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := classifyWork(tt.facts); got != tt.want {
				t.Fatalf("classifyWork() = %q, want %q", got, tt.want)
			}
		})
	}
}
