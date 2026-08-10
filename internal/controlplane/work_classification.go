package controlplane

import "strings"

type workClass string

const (
	workClassProduct   workClass = "product"
	workClassPatrol    workClass = "patrol"
	workClassScheduled workClass = "scheduled"
	workClassHelper    workClass = "helper"
	workClassService   workClass = "service"
)

type workClassificationFacts struct {
	title            string
	automationLinked bool
	scheduled        bool
	automationName   string
	automationText   string
}

// classifyWork uses durable task and Automation facts only. In particular, an
// ordinary untagged task is product work; words in its prose do not turn it
// into a service task.
func classifyWork(facts workClassificationFacts) workClass {
	lowerAutomation := strings.ToLower(facts.automationName + " " + facts.automationText)
	if facts.scheduled && strings.Contains(lowerAutomation, "factory pipeline patrol") {
		return workClassPatrol
	}
	if facts.scheduled {
		return workClassScheduled
	}
	if facts.automationLinked {
		return workClassService
	}
	title := strings.ToLower(strings.TrimSpace(facts.title))
	for _, prefix := range []string{"[helper]", "[debug]", "[service]", "[epic-plan]"} {
		if strings.HasPrefix(title, prefix) {
			return workClassHelper
		}
	}
	return workClassProduct
}
