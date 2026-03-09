# Diagrams

## 1) Full platform architecture
~~~text
Signal Sources -> Event Stream -> Distributed Workers -> Intelligence Core -> APIs/Execution
                                          |                 |
                                          v                 v
                                    Feature/Outcome Stores  Global Learning Graph
~~~

## 2) Learning loop
~~~text
signals -> features -> patterns -> recommendations -> simulations -> execution -> outcomes
        -> graph updates -> causal rules -> policy updates -> improved recommendations
~~~

## 3) Event flow
~~~text
producer services -> topic partitions -> consumer groups -> state stores -> metrics + alerts
~~~

## 4) Graph intelligence flow
~~~text
campaign context -> graph query -> strategy evidence -> simulation validation -> deployment
~~~

## 5) Simulation pipeline
~~~text
candidate strategies -> batch scheduler -> parallel simulation workers -> calibration -> ranking
~~~
