Uh hello everyone. [music] Uh I'm to uh

today we're going to talk about a shift

that's uh kind of happening quietly uh

underneath uh every I would say nearly

every retrieval system in production

today right um for for about two decades

I would say search was kind of built

around the assumption that uh users uh

express this fully formed intent right

that is no longer true uh interfaces

have changed right and user expectations

have changed

And the world in the past 5 years has

changed significantly, right? And search

systems that were kind of once pretty

deterministic uh and stateless, right?

Uh and kind of flew I would say like

brutally little now they need to behave

more like u distributed reasoning,

right? And my talk is basically about uh

how we get there and what was uh we kind

of fundamentally redesigned, right? So

let's kind of start with a problem right

um we're going to go through this in

like five chapters like one is you know

why information retrieval kind of breaks

under real world ambiguity

and then you know what happens when

retrieval kind of becomes a stateful

reasoning and some building blocks of uh

agentic systems u and what these systems

kind of look like uh in production.

uh finally uh the very uh open book

unknown question which is how does AGI

kind of dissolve this boundary between I

don't know search and understanding

right so this is essentially if you

think about it it's a systems

engineering view of uh next decade of

search um so let's kind of start with

why are classical approaches kind of

bend and break right um so with tracing

the progress that we've made in like

search architecture

u we had lexical pipelines right um

which is your PM25 DF these were very

deterministic and extremely fast um they

also relied on you know sparse

interpretations uh and they had no

semantic structure right they kind of

treated every token as an independent

kind of statistical event and these

systems um fell apart when vocabulary

diverged from user phrasing, right? And

then, you know, we enter the new era

which we're still in. Uh this is this

whole vector-based uh rag systems where

we introduce like embeddings and tense

representation and like semantic

similarity. Uh but they also came with

some new challenges, right? uh if you

look at uh uh chunking heristics or KN&N

latency right so a fundamentally

stateless generation step uh so as these

embeddings kind of got better and you

had like chunk collapses vector drifts

and uh irrelevance kind of became a big

operational cost

uh the next stage of evolution that

we're kind of heading into uh is an

agentic search where you know it's it's

an entirely different category um

instead of a single retrieval step we

kind of get this whole multi-term

reasoning um strategies tool calls and

state right so retrieval here becomes

part of a control loop and not an

endpoint so I would say this is not

search 2.0 Oh, it's just uh it's a

different computational model, right?

And the reason for that shift uh becomes

obvious when we look at uh user

behavior, right? So this kind of 2 + two

diagram here captures a fundamental

truth, right? Users are increasingly

operating in a high ambiguity and high

complexity region, right? Uh most

queries today are kind of underspecified

by design, right? And users say things

like okay say you know find that Python

memory thing from last week or you know

a laptop for editing

but

light right so if you think about static

information retrieval

uh that assumes that text is truth right

but what users are doing is they're

expressing partial intent here and not

instructions so that means

failure mode which is like your zero

session memory or like uh intent

collapse and you know if we think about

lexical brittleleness they're all

natural outcome of this whole

architectural mismatch right and the

system uh does exactly what you tell it

which is which is precisely the problem

here um let's try to make it a little

more concrete so

I mean the most common pattern in a

modern search is this whole uh say you

know this example the Python memory

thing from last week right um it's

incomplete it's fuzzy and it's partially

kind of recalled intent right and it

also has some temporal ground so this is

not a keyword kind of retrieval problem

uh it's basically an interpretation

problem so we need a system that can

detect entities here. Python is an

entity, right? Um and resolve some sort

of temporal constraints like last week

and get to classifying the domain which

is programming resources and finally

infer what is the missing structure

here. Is it like article, tutorial or

code snippet? Right? So without

reasoning this query is impossible to

answer very badly right and I think uh

this is kind of the canonical example

that motivates an agentic uh approach.

So

we move from a static retrieval to a

stateful reasoning.

Um so

let's kind of look at like the core

structure for an agentic search engine.

I've just kind of written in the this

whole agentic search state. uh right so

this holds uh the original query uh some

sort of a reformulation trajectory and

you have the embeddings that are

associated with each iteration

and set of retrieval strategies and some

confidence curves and uh diversity

metrics right now this is a session

local memory which means you have a very

consistent internal representation that

survives across across the tool calls

and across iterations, right? The

challenge here is how do you do adaptive

strategies? How do you kind of like

perform failure signal detection, right?

And

atomic component updates, right? And if

you think about even diversity analysis,

these are system problems and not like

model problems. So what we need is a

distributed stateful multi-turn

controller right and with that state we

can actually execute a controlled

reasoning loop um

the whole uh there's there's different

versions of this whole agentic search uh

architecture

um I think fundamentally I think treat

it as a reasoning pipeline right um we

had the python memory uh thing example

So that uh is a realistic conversion

process, right?

Because the result entropy is extremely

high and you have the system that is

essentially blind and

if you kind of go to the next version

which is Python memory leak detection,

right? You still have high entropy but

the strategy uh is ineffective, right?

And then

you have this whole uh each stage of the

loop. Uh if you look at it, we have the

query understanding here where we do

entity extraction,

intent classification and detection of

ambiguity. Um and then you move to

strategy selection which is pretty

dynamic, right? You have lexical,

semantic, graph-based, hybrid, all of

these approaches. uh and then moving on

to all the way to multiple backends that

are kind of orchestrated with like fault

tolerance. This this loop is

fundamentally I would say a form of

online optimization. Uh now to to kind

of build these systems we need solid uh

design principles here. uh and uh

so we have two philosophies I'm trying

to contrast in this slide. One is you

have your uh monolithic API which is a

single search endpoint. It has dozens of

parameters, right? Um these are brittle

for LLMs because they're

nondeterministic and um it's nearly

impossible to reason about them, right?

And then you have uh composable tools

here where these are atomic u

transparent functions like say you know

uh keyword search for example or

semantic search right these are serving

as primitives for the agent they kind of

make the agent uh the planning part of

the agent very tractable and you're

improving determinism here that means

you know it's debugging the you know

becomes simpler And uh managing a policy

space is also uh easier in that sense.

Um and those primitives only work if the

substrate here is understandable, right?

Um so

this is my uh you know like favorite

benchmarking slide here for search,

right? So if you [clears throat] take a

sing simple BM25, right? when it's

paired with an agent, it outperforms a

complex neural network uh that is

without an agent. Right? So agents need

predictable

distribution scores and semantics.

But when you have opaque read anchors

and blackbox embeddings that makes uh

reasoning difficult uh to to understand

like what is the cause and what is the

effect as well. And by contrast, I would

say that uh systems like very

transparent systems like BM25

um they make the agent hypothesis very

accurate and it's a refinement kind of

much more meaningful as well. So the

takeaway is your backend doesn't need to

be fancy. It needs to be uh predictable

here, right? And let's let's kind of

talk about uh a modern query uh

interpretation uh in a sense right. So

if you look at uh

our modern query systems which is uh

pretty dynamic in nature right um

how are we kind of looking at agentic

system performing yeah free text into

like a transforming that into a

structured meaning right a traditional

NLV pipelines were sequential and

brittle and what they produced was lean

linear labels and not reasoning

artifacts. Right? Now,

agentic interpretation instead it's

generates

some sort of a structured query type

semantic intent and temporal constraint.

Uh looking at our previous example,

right, and multiple hypothesis for any

kind of a disambiguation, right? So what

we're trying to build is a probabistic

space for interpretation and not a

single answer. So this kind of makes the

downstream strategies much more

targeted and uh it is this grounding uh

in like linguistics that enables uh

reasoning as well. And uh once you know

what the user intent is, you can

classify the task that they're kind of

performing. Um and

if you

these examples kind of show like the

intent specific feature vectors, right?

For example, for query which is laptop

for coding, right? The system kind of

emphasizes, you know, CPU, RAM, dev

environment. Uh now the same thing for a

video editing computer you're looking at

like GPU throughput maybe a display

surface uh and uh finally for a portable

workstation I think what's important is

the mobility and energy constraints

maybe right so this is structurally

different from the document embeddings

uh that we've been doing what we're

trying to do here is build query

embeddings that are conditioned on uh

intent Right. And you can see the

outcome. I mean, we've had like uh

roughly 35% lift in precision. Um not a

lot of latency overhead as well. So this

is uh you know high frequency semantic

inference. Um now

interpretation isn't enough right? We

need relevance and that requires uh uh

real kind of human feedback. So the

reality of things um

we have LML based uh relevance scoring

actually that has some useful prior but

it has some famous limitations that it

doesn't personalize right one and it

doesn't uh adapt to drift two and

it is not interpretable uh when it fails

right so a hyperl relevance basically uh

combines LLM signals with behavioral

feedback right um I have this whole

hybrid relevant scaling uh equation here

but basically what we're trying to do is

um the behavioral signals provide the

grounding and then your human feedback

corrects any model hallucinations

and you know we have a waiting that

gives us control as well and this kind

of closes the loop for retrieval to

reasoning to user and refinement

uh as well. Now

what is the uh you know what's the cost

or economics of this uh reasoning right

so

if you look at the table here

I'll just go through right um so you

know the first tier is like cache

patterns these are kind of like uh the

cost is essentially freeish uh and your

latency is like about 10 milliseconds

and these [clears throat] are like

deterministic and repeated interns and

then you move to distilled uh models

models where you know the latency is

maybe about 50 milliseconds inexpensive

um and it's used for like simple

reasoning and then you move on to single

pass agent which is which is where the

latency is like about 200 milliseconds

and the cost is becoming moderate as

well right uh and finally when we go

with full reasoning

uh the latency is likely about 500

milliseconds

high cost as well. So u so when we have

complex queries uh that we receive like

can some of these queries receive the

depth right and majority of the traffic

kind of still remains extremely

efficient but when we have complex

queries they receive these kind of depth

like this is um this is like the

economic backbone you might call as uh

for search and like agentic context. So

what what does it kind of look like in a

real system, right? Um so

a modern uh production grade agent

search system, you have uh query routing

that's happening. Um so you know

using your top of the shelf flink uh

streams uh for any real-time complexity

and then we have a cache layer and then

an agent service which is a stateful

orchestrator um say now you can build it

on temporal right and then uh you have a

search back end which is hybrid lexical

plus vector retrieval uh along with like

a multi-stage ranking right And uh

finally you know u this is what it looks

like when kind of like reasoning is

meeting our production constraints. U we

have about u uh 100 millisecond in terms

of like p5 latency and uh 6% uh zero

result rate. Um let's let's talk about

where this whole uh you know trajectory

kind of leads.

Um I think the future of the search is

an interesting topic. uh the next decade

basically brings

uh three kind of like horizons

uh I think uh near-term as an end of

this year right we're still looking at

like multi-turn clarification or some

sort of a cross session memory and we

are doing real-time user learning right

now think about horizon about 2026 we're

looking at like domain specialized

agents or microservices for reasoning.

This is already happening in some spaces

and how do we do anticipate research as

well. Um in the long run, you know,

you're looking at ambient intelligence

which is something that's always

available uh multimodal agents and

they're operating across all your

devices and context, right? such kind of

becomes conversational here and um

conversation becomes predictive and uh

predictive becomes embedded. So uh

that's that's the that's the realm of

future for search and beyond that uh

on philos philosophical note search may

disappear entirely right so what what

does it look like when we have AGI right

uh if an AGI fully understands

um intent

context and uh the world state right

what what does such become Uh so I kind

of posit that there may be three

futures. uh one is search resolves uh

AGI anticipates uh needs right you have

information flows without explicit

squaries that's that's one or two you

know we have AGI that kind of routes

knowledge between specialized agents uh

or humans right and [clears throat]

finally we may also have uh something

that's called uh reality querying where

your simulation is basically becoming a

query primitive the the what if becomes

uh you know computable at scale right I

do think there's a bit of a paradox here

uh the better your search is getting the

less it's going to resemble search I

think at some point retrieval uh becomes

uh understanding

yeah um

yeah I think uh it's going to be

interesting to see where the reality

leads uh in the next uh decade and uh

with that uh you know let's let's add

I do think uh we're at a moment where

search is transforming into something

fundamentally more capable and uh more

aligned with how humans actually think.

Uh, thank you

Tosh. That was mindbending.

I was just completely transfixed

throughout. So, it's there there's

something I don't know if meditative was

uh is is the right word here, but it's

uh just deeply immersive in the way that

you were presenting it. I think it's

also not if you go back one slide

it's in some ways it reminds me that you

know that that future of search deol

dissolving into understanding um because

it is anticipatory. I imagine that

something similar might have happened in

YouTube. I mean I just it feels like

back in the day I used to spend time on

YouTube by searching by using the search

bar and as recommendation became better

it's just who uses the search bar on

YouTube I don't know right and so do you

imagine that it would be a

transformation that might at least along

this path that kind of resembles that

where the system is

you're saying predicting embedding

surfacing almost recommending ing uh the

right piece of content at the right

time.

Yeah, that's a

I would say I think it's it's it's a

very kind of like uh it's a it's a good

observation, right? What's what's kind

of happening with uh YouTube

recommendations is I think it's a really

good early signal of where search is

headed. Um I do think you know

especially modern recommendation systems

where you have like uh these YouTube tik

tok or Instagram reels we've kind of

shifted from this whole how do we

retrieve relevant items to predict the

next embedding. I think uh

the

if YouTube recommendation systems were

modeling hey you know what are you

probably going to watch next right the

future systems model would be uh what

are you going to probably going to ask

next right so I think in both cases I

the system is no longer kind of matching

but it's rather forecasting I think that

is where the essence of this whole

search kind of dissolving into

understanding uh comes from

yeah I mean I I see it now just with the

way that I interact with CHGPT, right?

Where like it's it's sure I I give it

this seed of thought and then for the

next five six prompts I mostly say sure.

Yeah, go for it. Okay, I want to see it.

Right. And it is almost it's pulling me

into the right. It is showing me what I

should be interested in. type of

recommendation, but I I imagine it's

sort of forecastable internally on their

end.

Very cool. We have a couple of questions

here uh from Aporva. For hybrid scoring,

do you have inputs on how to weigh the

different terms?

Yeah. Uh basically

I think if you look at uh hybrid scoring

the the main thing is

how are you combining a few things

right? One is LLM relevance clicks or

you know dwell time negative signals. So

what we're trying to do is we're

building a multi-objective optimization

function right over any kind of

heterogeneous signals that we have. So

you don't want to treat these signals

symmetrically um because each of them is

going to carry different statistical

properties right. So here's how uh you

know I would kind of think about it when

is LLM relevance is kind of it's a good

prior to have but it's not a proper

ground tool right and you have your CTR

and dwell time which are like high

signal but high variance. So they're

they're they're good short-term

indicators for relevance.

Uh but they're very sensitive to say

some things like I don't know

personalization position bias. So you

can typically apply like a sharper

normalization u say you know something

like a position normalized click model

right and then

say if a user says look this is not

helpful or uh it kind of does a fast

bounce then you know you actually have

the negative feedback that's a low

frequency

but extremely high precision right so we

give disproportionate influence to that

sometimes even maybe a veto because

negative signals tend to be sparse uh

but they're ambiguous. So I think the

right way to kind of think about hybrid

scoring is not a fixed formula per se

but rather how do we think about it as

an adaptive policy right

that changes uh the weights change.

Yeah, remember maybe like different

regimes where one factor influences more

than the other,

right?

We got another one. Uh, Apurva, any

inputs you might share on the evaluation

phase [clears throat] either of

retrieval or of agent paths?

Yeah. So I don't think I covered uh

evaluation of this uh tech so far but um

I think fundamentally evaluating agentic

systems are I would say they're they're

different from like your traditional IR

problems because

we are no longer kind of measuring a

single hop right you're you're measuring

a trajectory right um so

you know in a in a dynamic u agentic

path I think

the evaluation metrics that I would kind

of look at. It's more like a planning

algorithm. So what is a convergence

rate? How many steps does it take the

reasoning loop before termination,

right? Or how many distinct strategies

were explored? Was it like lexical first

versus like graph first, right? And

quality where you how much information

gain is happening per iteration. Mhm.

Um I think uh it's it's pretty layered

because retrieval kind of tells you this

whole signal fidelity and uh agent deval

tells you policy quality right and then

the combination of the soul retrieval

plus agent is going to give you uh a

system intelligence. So yeah uh I would

say we can measure both the both of them

independently and then together and then

the joint metrics such as like

convergence rate or entropy reduction

and the the quality of the reasoning

path they they kind of tell us whether

this entire loop is working uh as we

wanted it to. Yeah,

I see that you're I'll ask you a final

question on my end. You've hiked Everest

base camp, Kilimanjaro and Patagonia. Is

that yet? You haven't yet climbed

anything in Euseite. Do you think that

if search fully dissolves and

disappears, you'll finally have time to

go to?

Yeah, I I really hope so. Uh it's been

when I try to

climb,

something or the other happens. Uh this

time around we actually have a new baby

in the house which [laughter] is a good

thing and now we're planning to take the

date. So let's let's hope uh I do the

hike before uh AGI happens.

I'm crossing my fingers that that

happens. Tosh, thank you very much for

coming and joining us. I think we might

have some more questions in the chat. So

if you want to drop in the chat and if

people can connect with you however you

like, Twitter, LinkedIn,

whichever method you use, I think it'd

be useful. uh if you do do you ever

write about these things in the future

of search?

Uh I think I do have a book in the

making but I'm planning to publish it by

size blog as well. Uh and you know

people can connect with me on LinkedIn.

I'll drop my uh LinkedIn

as well.

Please do. Thank you very much for

coming. It was a pleasure from you. All

right. Thanks everyone. [music]